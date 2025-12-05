"""
Bot Telegram para pesquisar no Diário Oficial dos Municípios
https://www.diarioficialdosmunicipios.org/edicao_atual.html
"""

import os
import re
import json
import logging
import requests
import unicodedata
import asyncio
from io import BytesIO
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.error import NetworkError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import fitz  # PyMuPDF para destacar palavras no PDF
from dotenv import load_dotenv


def normalize_text(text: str) -> str:
    """Remove acentos e normaliza texto para busca."""
    # Normaliza para forma NFD (decompõe caracteres acentuados)
    normalized = unicodedata.normalize('NFD', text)
    # Remove caracteres de combinação (acentos)
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents.lower()

# Carrega variáveis de ambiente
load_dotenv()

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token do bot (coloque no arquivo .env)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ID do chat para notificações automáticas
NOTIFY_CHAT_ID = os.getenv("NOTIFY_CHAT_ID")

# URL base do Diário Oficial dos Municípios
BASE_URL = "https://www.diarioficialdosmunicipios.org"
EDICAO_ATUAL_URL = f"{BASE_URL}/edicao_atual.html"

# Palavras-chave padrão
DEFAULT_KEYWORDS = [
    "Convita",
    "mg gestão ambiental",
    "Bioparque Zoobotânico",
    "r m estrutura e pavimentação",
    "Luiz Francisco do Rego Monteiro",
    "Lumig",
    "Molla"
]

# Edição base conhecida (atualizar periodicamente ou usar busca automática)
EDITION_BASE = 5462  # Edição de 04/12/2025

# Diretório para cache do PDF
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# Arquivo para salvar usuários inscritos
SUBSCRIBERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscribers.json")


class DiarioOficialBot:
    def __init__(self):
        self.user_keywords = {}  # Armazena palavras-chave por usuário
        self.subscribers = set()  # Usuários inscritos para notificações
        self.cached_edition = None  # Cache da edição atual
        self.cached_pdf_path = None  # Caminho do PDF em cache
        
        # Cria diretório de cache se não existir
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        
        # Carrega usuários inscritos
        self.load_subscribers()
    
    def load_subscribers(self) -> None:
        """Carrega usuários inscritos do arquivo JSON."""
        try:
            if os.path.exists(SUBSCRIBERS_FILE):
                with open(SUBSCRIBERS_FILE, "r") as f:
                    data = json.load(f)
                    self.subscribers = set(data.get("subscribers", []))
                    self.user_keywords = {int(k): v for k, v in data.get("keywords", {}).items()}
                logger.info(f"Carregados {len(self.subscribers)} usuário(s) inscrito(s)")
        except Exception as e:
            logger.error(f"Erro ao carregar subscribers: {e}")
            self.subscribers = set()
    
    def save_subscribers(self) -> None:
        """Salva usuários inscritos no arquivo JSON."""
        try:
            data = {
                "subscribers": list(self.subscribers),
                "keywords": {str(k): v for k, v in self.user_keywords.items()}
            }
            with open(SUBSCRIBERS_FILE, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Salvos {len(self.subscribers)} usuário(s) inscrito(s)")
        except Exception as e:
            logger.error(f"Erro ao salvar subscribers: {e}")
    
    def add_subscriber(self, chat_id: int) -> bool:
        """Adiciona um usuário à lista de inscritos."""
        if chat_id not in self.subscribers:
            self.subscribers.add(chat_id)
            self.save_subscribers()
            logger.info(f"Novo inscrito: {chat_id}")
            return True
        return False
    
    def remove_subscriber(self, chat_id: int) -> bool:
        """Remove um usuário da lista de inscritos."""
        if chat_id in self.subscribers:
            self.subscribers.discard(chat_id)
            self.save_subscribers()
            logger.info(f"Inscrito removido: {chat_id}")
            return True
        return False

    def find_latest_edition(self, start_from: int = EDITION_BASE) -> int:
        """Encontra a edição mais recente testando URLs."""
        edition = start_from
        
        # Tenta encontrar edições mais recentes (verifica até 30 edições à frente)
        for i in range(30):
            test_edition = edition + i
            url = f"{BASE_URL}/intranet/_lib/file/doc/pdfs/novo/{test_edition}/DM_{test_edition}.pdf"
            try:
                response = requests.head(url, timeout=10)
                if response.status_code == 200:
                    edition = test_edition
                else:
                    break
            except:
                break
        
        logger.info(f"Edição mais recente encontrada: {edition}")
        return edition

    def get_current_edition_info(self) -> dict:
        """Obtém informações da edição atual do Diário Oficial."""
        try:
            # Primeiro tenta pegar da página HTML
            response = requests.get(EDICAO_ATUAL_URL, timeout=30)
            response.raise_for_status()
            html_content = response.text

            # Extrai número da edição e data
            edition_match = re.search(r'Edição\s*(\d+),\s*(\d{2}/\d{2}/\d{4})', html_content)
            
            if edition_match:
                edition_number = edition_match.group(1)
                edition_date = edition_match.group(2)
                pdf_url = f"{BASE_URL}/intranet/_lib/file/doc/pdfs/novo/{edition_number}/DM_{edition_number}.pdf"
                
                return {
                    "edition_number": edition_number,
                    "edition_date": edition_date,
                    "pdf_url": pdf_url,
                    "success": True
                }
            
            # Se não encontrou no HTML (página com JavaScript), busca a edição mais recente
            logger.info("HTML não contém edição, buscando edição mais recente...")
            edition_number = self.find_latest_edition()
            pdf_url = f"{BASE_URL}/intranet/_lib/file/doc/pdfs/novo/{edition_number}/DM_{edition_number}.pdf"
            
           
            from datetime import datetime
            edition_date = datetime.now().strftime("%d/%m/%Y")
            
            return {
                "edition_number": str(edition_number),
                "edition_date": edition_date,
                "pdf_url": pdf_url,
                "success": True
            }
            
        except requests.RequestException as e:
            logger.error(f"Erro ao acessar página: {e}")
            
           
            edition_number = EDITION_BASE
            pdf_url = f"{BASE_URL}/intranet/_lib/file/doc/pdfs/novo/{edition_number}/DM_{edition_number}.pdf"
            from datetime import datetime
            edition_date = datetime.now().strftime("%d/%m/%Y")
            
            return {
                "edition_number": str(edition_number),
                "edition_date": edition_date,
                "pdf_url": pdf_url,
                "success": True
            }

    def get_cached_pdf(self, edition_number: str) -> BytesIO | None:
        """Retorna o PDF do cache se existir."""
        cache_file = os.path.join(CACHE_DIR, f"DM_{edition_number}.pdf")
        
        if os.path.exists(cache_file):
            logger.info(f"Usando PDF em cache: {cache_file}")
            with open(cache_file, "rb") as f:
                return BytesIO(f.read())
        return None

    def save_pdf_to_cache(self, edition_number: str, pdf_bytes: BytesIO) -> None:
        """Salva o PDF no cache."""
        cache_file = os.path.join(CACHE_DIR, f"DM_{edition_number}.pdf")
        pdf_bytes.seek(0)
        
        with open(cache_file, "wb") as f:
            f.write(pdf_bytes.read())
        
        pdf_bytes.seek(0)
        logger.info(f"PDF salvo em cache: {cache_file}")

    def download_pdf(self, url: str, edition_number: str = None) -> BytesIO | None:
        """Baixa o PDF e retorna como BytesIO. Usa cache se disponível."""
        # Tenta usar cache primeiro
        if edition_number:
            cached = self.get_cached_pdf(edition_number)
            if cached:
                return cached
        
        try:
            logger.info(f"Baixando PDF: {url}")
            # Timeout alto pois o PDF pode ter centenas de páginas (~500MB)
            response = requests.get(url, timeout=600)  # 10 minutos
            response.raise_for_status()
            pdf_bytes = BytesIO(response.content)
            
            # Salva no cache
            if edition_number:
                self.save_pdf_to_cache(edition_number, pdf_bytes)
            
            return pdf_bytes
        except requests.RequestException as e:
            logger.error(f"Erro ao baixar PDF: {e}")
            return None

    def clear_cache(self) -> int:
        """Limpa o cache de PDFs. Retorna quantidade de arquivos removidos."""
        count = 0
        if os.path.exists(CACHE_DIR):
            for file in os.listdir(CACHE_DIR):
                if file.endswith(".pdf"):
                    os.remove(os.path.join(CACHE_DIR, file))
                    count += 1
        return count

    def search_keywords_in_pdf(self, pdf_bytes: BytesIO, keywords: list) -> dict:
        """Pesquisa palavras-chave no PDF e retorna ocorrências."""
        results = {keyword: {"count": 0, "pages": [], "contexts": []} for keyword in keywords}
        
        try:
            pdf_bytes.seek(0)
            doc = fitz.open(stream=pdf_bytes.read(), filetype="pdf")
            total_pages = len(doc)
            
            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text()
                if not text:
                    continue
                
                # Normaliza texto removendo quebras de linha e espaços extras para melhor busca
                text_single_line = ' '.join(text.split())  # Remove quebras de linha e espaços múltiplos
                text_normalized = normalize_text(text_single_line)
                text_lower = text_single_line.lower()
                
                for keyword in keywords:
                    keyword_clean = ' '.join(keyword.split())  # Normaliza keyword também
                    keyword_normalized = normalize_text(keyword_clean)
                    keyword_lower = keyword_clean.lower()
                    
                    # Conta ocorrências (busca com e sem acentos)
                    count = text_normalized.count(keyword_normalized)
                    if count == 0:
                        count = text_lower.count(keyword_lower)
                    
                    if count > 0:
                        results[keyword]["count"] += count
                        if (page_num + 1) not in results[keyword]["pages"]:
                            results[keyword]["pages"].append(page_num + 1)
                        
                        # Extrai contexto usando texto normalizado para encontrar trechos relevantes
                        # Procura no texto normalizado e depois encontra a posição original
                        keyword_pos = text_lower.find(keyword_lower)
                        while keyword_pos != -1:
                            start_pos = max(0, keyword_pos - 50)
                            end_pos = min(len(text_single_line), keyword_pos + len(keyword_clean) + 50)
                            context = text_single_line[start_pos:end_pos].strip()
                            if context and context not in results[keyword]["contexts"]:
                                results[keyword]["contexts"].append(f"...{context}...")
                                if len(results[keyword]["contexts"]) >= 5:  # Máximo 5 contextos
                                    break
                            keyword_pos = text_lower.find(keyword_lower, keyword_pos + 1)
            
            doc.close()
            return {"success": True, "results": results, "total_pages": total_pages}
            
        except Exception as e:
            logger.error(f"Erro ao processar PDF: {e}")
            return {"success": False, "error": str(e)}

    def highlight_keywords_in_pdf(self, pdf_bytes: BytesIO, keywords: list, found_results: dict) -> BytesIO | None:
        """Destaca as palavras-chave e extrai APENAS as páginas que contêm as palavras."""
        try:
            pdf_bytes.seek(0)
            doc = fitz.open(stream=pdf_bytes.read(), filetype="pdf")
            
            # Coleta todas as páginas que têm palavras-chave
            pages_with_keywords = set()
            for keyword, data in found_results.items():
                if data.get("count", 0) > 0:
                    for page in data.get("pages", []):
                        pages_with_keywords.add(page - 1)  # Converte para índice 0-based
            
            if not pages_with_keywords:
                doc.close()
                return None
            
            # Cores diferentes para cada palavra-chave
            colors = [
                (1, 1, 0),      # Amarelo
                (0.5, 1, 0.5),  # Verde claro
                (1, 0.7, 0.7),  # Rosa
                (0.7, 0.85, 1), # Azul claro
                (1, 0.8, 0.5),  # Laranja
                (0.9, 0.7, 1),  # Roxo claro
                (0.5, 1, 1),    # Ciano
            ]
            
            # Cria novo documento apenas com as páginas relevantes
            new_doc = fitz.open()
            highlighted_count = 0
            
            for page_num in sorted(pages_with_keywords):
                if page_num < len(doc):
                    # Copia a página para o novo documento
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    
                    # Pega a página no novo documento (última adicionada)
                    new_page = new_doc[-1]
                    
                    # Destaca as palavras-chave
                    for idx, keyword in enumerate(keywords):
                        if found_results.get(keyword, {}).get("count", 0) > 0:
                            color = colors[idx % len(colors)]
                            
                            # Busca a palavra-chave inteira primeiro
                            text_instances = new_page.search_for(keyword, quads=True)
                            
                            # Se não encontrar, busca cada palavra individualmente
                            # (para casos onde o texto está quebrado em linhas)
                            if not text_instances:
                                words = keyword.split()
                                for word in words:
                                    if len(word) >= 3:  # Ignora palavras muito curtas
                                        word_instances = new_page.search_for(word, quads=True)
                                        text_instances.extend(word_instances)
                            
                            for inst in text_instances:
                                highlight = new_page.add_highlight_annot(inst)
                                highlight.set_colors(stroke=color)
                                highlight.update()
                                highlighted_count += 1
            
            # Salva PDF modificado
            output = BytesIO()
            new_doc.save(output)
            new_doc.close()
            doc.close()
            output.seek(0)
            
            logger.info(f"PDF destacado com {highlighted_count} ocorrências em {len(pages_with_keywords)} páginas")
            return output
            
        except Exception as e:
            logger.error(f"Erro ao destacar PDF: {e}")
            return None


# Instância global do bot
diario_bot = DiarioOficialBot()


def get_user_keywords(user_id: int) -> list:
    """Retorna palavras-chave do usuário ou as padrão."""
    if user_id in diario_bot.user_keywords and diario_bot.user_keywords[user_id]:
        return diario_bot.user_keywords[user_id]
    return DEFAULT_KEYWORDS.copy()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start - Mensagem de boas-vindas."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Log do chat_id para facilitar configuração
    logger.info(f"Usuário iniciou bot - User ID: {user_id}, Chat ID: {chat_id}")
    
    # Registra usuário para notificações automáticas
    is_new = diario_bot.add_subscriber(chat_id)
    
    # Inicializa palavras-chave padrão para o usuário
    if user_id not in diario_bot.user_keywords:
        diario_bot.user_keywords[user_id] = DEFAULT_KEYWORDS.copy()
        diario_bot.save_subscribers()  # Salva as palavras-chave também
    
    keywords_list = "\n".join([f"• {kw}" for kw in get_user_keywords(user_id)])
    
    # Mensagem de inscrição
    subscription_info = ""
    if is_new:
        subscription_info = "\n\n✅ *Você foi inscrito nas notificações automáticas!*"
    
    total_subscribers = len(diario_bot.subscribers)
    
    welcome_message = f"""
🏛️ *Bot do Diário Oficial dos Municípios*

Bem-vindo! Este bot pesquisa palavras-chave no Diário Oficial dos Municípios do Piauí.

*Comandos disponíveis:*
/start - Exibe esta mensagem
/edicao - Mostra a edição atual
/baixar - Baixa o PDF da edição atual
/palavras - Lista suas palavras-chave
/adicionar <palavra> - Adiciona uma palavra-chave
/remover <palavra> - Remove uma palavra-chave
/limpar - Remove todas as palavras-chave
/resetar - Volta para palavras-chave padrão
/pesquisar - Pesquisa suas palavras-chave na edição atual
/buscar <termo> - Busca um termo específico (sem salvar)
/cache - Limpa cache (para baixar nova edição)
/desinscrever - Cancela notificações automáticas

*Suas palavras-chave atuais:*
{keywords_list}

⏰ *Pesquisa automática:* Diariamente às 12:00
👥 *Usuários inscritos:* {total_subscribers}{subscription_info}

Use /pesquisar para buscar agora!
"""
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def get_edition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /edicao - Mostra informações da edição atual."""
    await update.message.reply_text("🔍 Buscando edição atual...")
    
    info = diario_bot.get_current_edition_info()
    
    if info["success"]:
        message = f"""
📰 *Diário Oficial dos Municípios*

📅 *Data:* {info['edition_date']}
📄 *Edição:* {info['edition_number']}
🔗 [Link do PDF]({info['pdf_url']})
"""
        keyboard = [[InlineKeyboardButton("📥 Baixar PDF", callback_data=f"download_{info['edition_number']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"❌ Erro: {info['error']}")


async def download_edition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /baixar - Baixa o PDF da edição atual."""
    await update.message.reply_text("⏳ Baixando PDF... Isso pode demorar alguns segundos.")
    
    info = diario_bot.get_current_edition_info()
    
    if not info["success"]:
        await update.message.reply_text(f"❌ Erro: {info['error']}")
        return
    
    pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
    
    if pdf_bytes:
        pdf_bytes.seek(0)
        try:
            await update.message.reply_document(
                document=pdf_bytes,
                filename=f"DM_{info['edition_number']}.pdf",
                caption=f"📰 Diário Oficial - Edição {info['edition_number']} ({info['edition_date']})"
            )
        except NetworkError as e:
            if "Request Entity Too Large" in str(e):
                await update.message.reply_text(
                    "❌ *Arquivo muito grande!*\n\n"
                    "O PDF é maior que o limite de 50MB do Telegram.\n"
                    "Use `/pesquisar` para receber apenas as páginas com as palavras-chave.",
                    parse_mode="Markdown"
                )
            else:
                raise e
    else:
        await update.message.reply_text("❌ Erro ao baixar o PDF. Tente novamente mais tarde.")


async def list_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /palavras - Lista palavras-chave do usuário."""
    user_id = update.effective_user.id
    keywords = get_user_keywords(user_id)
    
    if keywords:
        keywords_list = "\n".join([f"• {kw}" for kw in keywords])
        message = f"🔑 *Suas palavras-chave:*\n\n{keywords_list}"
    else:
        message = "📝 Você não tem palavras-chave cadastradas.\nUse `/adicionar <palavra>` para adicionar."
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /adicionar - Adiciona uma palavra-chave."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Use: `/adicionar <palavra-chave>`", parse_mode="Markdown")
        return
    
    keyword = " ".join(context.args).strip()
    
    if user_id not in diario_bot.user_keywords:
        diario_bot.user_keywords[user_id] = DEFAULT_KEYWORDS.copy()
    
    if keyword.lower() in [kw.lower() for kw in diario_bot.user_keywords[user_id]]:
        await update.message.reply_text(f"⚠️ A palavra-chave '{keyword}' já existe.")
        return
    
    diario_bot.user_keywords[user_id].append(keyword)
    await update.message.reply_text(f"✅ Palavra-chave '{keyword}' adicionada com sucesso!")


async def remove_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /remover - Remove uma palavra-chave."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Use: `/remover <palavra-chave>`", parse_mode="Markdown")
        return
    
    keyword = " ".join(context.args).strip()
    
    if user_id not in diario_bot.user_keywords:
        diario_bot.user_keywords[user_id] = DEFAULT_KEYWORDS.copy()
    
    keywords = diario_bot.user_keywords[user_id]
    
    # Procura case-insensitive
    for kw in keywords:
        if kw.lower() == keyword.lower():
            diario_bot.user_keywords[user_id].remove(kw)
            await update.message.reply_text(f"✅ Palavra-chave '{kw}' removida com sucesso!")
            return
    
    await update.message.reply_text(f"⚠️ Palavra-chave '{keyword}' não encontrada.")


async def clear_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /limpar - Remove todas as palavras-chave."""
    user_id = update.effective_user.id
    diario_bot.user_keywords[user_id] = []
    await update.message.reply_text("✅ Todas as palavras-chave foram removidas.")


async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /cache - Limpa o cache de PDFs."""
    count = diario_bot.clear_cache()
    if count > 0:
        await update.message.reply_text(f"🗑️ Cache limpo! {count} arquivo(s) removido(s).\nO próximo download irá baixar o PDF atualizado.")
    else:
        await update.message.reply_text("📁 Cache já está vazio.")


async def reset_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /resetar - Volta para palavras-chave padrão."""
    user_id = update.effective_user.id
    diario_bot.user_keywords[user_id] = DEFAULT_KEYWORDS.copy()
    
    keywords_list = "\n".join([f"• {kw}" for kw in DEFAULT_KEYWORDS])
    await update.message.reply_text(
        f"✅ Palavras-chave resetadas para o padrão:\n\n{keywords_list}",
        parse_mode="Markdown"
    )


async def search_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /pesquisar - Pesquisa palavras-chave no PDF."""
    user_id = update.effective_user.id
    keywords = get_user_keywords(user_id)
    
    if not keywords:
        await update.message.reply_text(
            "❌ Você não tem palavras-chave cadastradas.\nUse `/adicionar <palavra>` primeiro.",
            parse_mode="Markdown"
        )
        return
    
    # Obtém informações da edição
    info = diario_bot.get_current_edition_info()
    if not info["success"]:
        await update.message.reply_text(f"❌ Erro: {info['error']}")
        return
    
    # Verifica se já tem cache
    has_cache = diario_bot.get_cached_pdf(info["edition_number"]) is not None
    if has_cache:
        await update.message.reply_text("🔍 Analisando PDF (usando cache)... Aguarde.")
    else:
        await update.message.reply_text("🔍 Baixando e analisando PDF... Aguarde (pode demorar alguns minutos).")
    
    # Baixa o PDF (usa cache se disponível)
    pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
    if not pdf_bytes:
        await update.message.reply_text("❌ Erro ao baixar o PDF.")
        return
    
    # Pesquisa palavras-chave
    search_results = diario_bot.search_keywords_in_pdf(pdf_bytes, keywords)
    
    if not search_results["success"]:
        await update.message.reply_text(f"❌ Erro ao processar PDF: {search_results['error']}")
        return
    
    # Monta mensagem de resultado
    message = f"📰 *Resultado da Pesquisa*\n"
    message += f"📅 Edição {info['edition_number']} - {info['edition_date']}\n"
    message += f"📄 Total de páginas: {search_results['total_pages']}\n\n"
    
    found_any = False
    found_keywords = []
    
    for keyword, data in search_results["results"].items():
        if data["count"] > 0:
            found_any = True
            found_keywords.append(keyword)
            pages_str = ", ".join(map(str, data["pages"][:10]))  # Máximo 10 páginas
            message += f"✅ *{keyword}*\n"
            message += f"   📊 Ocorrências: {data['count']}\n"
            message += f"   📄 Páginas: {pages_str}\n"
            
            if data["contexts"]:
                message += f"   📝 Contexto:\n"
                for ctx in data["contexts"][:2]:  # Máximo 2 contextos
                    ctx_clean = ctx[:150].replace("*", "").replace("_", "").replace("`", "")
                    message += f"   _{ctx_clean}..._\n"
            message += "\n"
        else:
            message += f"❌ *{keyword}*: Não encontrado\n\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")
    
    # Se encontrou algo, gera PDF com destaques
    if found_any:
        await update.message.reply_text("✨ Gerando PDF com palavras destacadas (apenas páginas relevantes)...")
        
        # Baixa o PDF novamente para destacar (usa cache)
        pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
        if pdf_bytes:
            highlighted_pdf = diario_bot.highlight_keywords_in_pdf(
                pdf_bytes, 
                keywords, 
                search_results["results"]
            )
            
            if highlighted_pdf:
                # Calcula quantas páginas tem o PDF destacado
                pages_found = set()
                for kw, data in search_results["results"].items():
                    pages_found.update(data.get("pages", []))
                
                try:
                    await update.message.reply_document(
                        document=highlighted_pdf,
                        filename=f"DM_{info['edition_number']}_DESTACADO.pdf",
                        caption=f"📰 Edição {info['edition_number']}\n📄 Contém apenas {len(pages_found)} página(s) com as palavras encontradas\n🔍 Destacado: {', '.join(found_keywords)}"
                    )
                except NetworkError as e:
                    if "Request Entity Too Large" in str(e):
                        await update.message.reply_text(
                            f"❌ *Arquivo muito grande!*\n\n"
                            f"O PDF com {len(pages_found)} páginas destacadas excede o limite de 50MB do Telegram.\n\n"
                            f"📄 *Páginas encontradas:*\n{', '.join(map(str, sorted(pages_found)[:50]))}"
                            f"{'...' if len(pages_found) > 50 else ''}\n\n"
                            f"💡 Tente pesquisar termos mais específicos para reduzir o número de páginas.",
                            parse_mode="Markdown"
                        )
                    else:
                        raise e
            else:
                await update.message.reply_text("⚠️ Não foi possível gerar o PDF destacado. Enviando PDF original...")
                pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
                if pdf_bytes:
                    pdf_bytes.seek(0)
                    await update.message.reply_document(
                        document=pdf_bytes,
                        filename=f"DM_{info['edition_number']}.pdf",
                        caption=f"📰 Diário Oficial - Edição {info['edition_number']}"
                    )


async def quick_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /buscar - Busca um termo específico sem salvar."""
    if not context.args:
        await update.message.reply_text("❌ Use: `/buscar <termo>`", parse_mode="Markdown")
        return
    
    search_term = " ".join(context.args).strip()
    
    # Obtém informações da edição
    info = diario_bot.get_current_edition_info()
    if not info["success"]:
        await update.message.reply_text(f"❌ Erro: {info['error']}")
        return
    
    # Verifica se já tem cache
    has_cache = diario_bot.get_cached_pdf(info["edition_number"]) is not None
    if has_cache:
        await update.message.reply_text(f"🔍 Buscando '{search_term}' (usando cache)... Aguarde.")
    else:
        await update.message.reply_text(f"🔍 Baixando PDF e buscando '{search_term}'... Aguarde (pode demorar alguns minutos).")
    
    # Baixa o PDF (usa cache se disponível)
    pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
    if not pdf_bytes:
        await update.message.reply_text("❌ Erro ao baixar o PDF.")
        return
    
    # Pesquisa o termo
    search_results = diario_bot.search_keywords_in_pdf(pdf_bytes, [search_term])
    
    if not search_results["success"]:
        await update.message.reply_text(f"❌ Erro ao processar PDF: {search_results['error']}")
        return
    
    # Monta mensagem de resultado
    data = search_results["results"][search_term]
    
    if data["count"] > 0:
        pages_str = ", ".join(map(str, data["pages"][:15]))
        message = f"✅ *Termo encontrado!*\n\n"
        message += f"🔑 *{search_term}*\n"
        message += f"📊 Ocorrências: {data['count']}\n"
        message += f"📄 Páginas: {pages_str}\n\n"
        
        if data["contexts"]:
            message += f"📝 *Contextos:*\n"
            for ctx in data["contexts"][:3]:
                ctx_clean = ctx[:200].replace("*", "").replace("_", "").replace("`", "")
                message += f"• _{ctx_clean}_\n\n"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        
        # Gera PDF com destaque
        await update.message.reply_text("✨ Gerando PDF com termo destacado (apenas páginas relevantes)...")
        
        pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
        if pdf_bytes:
            highlighted_pdf = diario_bot.highlight_keywords_in_pdf(
                pdf_bytes, 
                [search_term], 
                search_results["results"]
            )
            
            if highlighted_pdf:
                pages_count = len(data.get("pages", []))
                pages_list = data.get("pages", [])
                try:
                    await update.message.reply_document(
                        document=highlighted_pdf,
                        filename=f"DM_{info['edition_number']}_DESTACADO.pdf",
                        caption=f"📰 Edição {info['edition_number']}\n📄 Contém apenas {pages_count} página(s) com o termo\n🔍 Destacado: {search_term}"
                    )
                except NetworkError as e:
                    if "Request Entity Too Large" in str(e):
                        await update.message.reply_text(
                            f"❌ *Arquivo muito grande!*\n\n"
                            f"O PDF com {pages_count} páginas destacadas excede o limite de 50MB do Telegram.\n\n"
                            f"📄 *Páginas onde '*{search_term}*' foi encontrado:*\n"
                            f"{', '.join(map(str, sorted(pages_list)[:50]))}"
                            f"{'...' if len(pages_list) > 50 else ''}\n\n"
                            f"💡 Tente pesquisar termos mais específicos para reduzir o número de páginas.",
                            parse_mode="Markdown"
                        )
                    else:
                        raise e
    else:
        message = f"❌ Termo '*{search_term}*' não encontrado na edição {info['edition_number']}."
        await update.message.reply_text(message, parse_mode="Markdown")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa callbacks dos botões inline."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("download_"):
        edition_number = query.data.replace("download_", "")
        pdf_url = f"{BASE_URL}/intranet/_lib/file/doc/pdfs/novo/{edition_number}/DM_{edition_number}.pdf"
        
        await query.message.reply_text("⏳ Baixando PDF...")
        
        pdf_bytes = diario_bot.download_pdf(pdf_url, edition_number)
        
        if pdf_bytes:
            pdf_bytes.seek(0)
            try:
                await query.message.reply_document(
                    document=pdf_bytes,
                    filename=f"DM_{edition_number}.pdf",
                    caption=f"📰 Diário Oficial - Edição {edition_number}"
                )
            except NetworkError as e:
                if "Request Entity Too Large" in str(e):
                    await query.message.reply_text(
                        "❌ *Arquivo muito grande!*\n\n"
                        "O PDF é maior que o limite de 50MB do Telegram.\n"
                        "Use `/pesquisar` para receber apenas as páginas com as palavras-chave.",
                        parse_mode="Markdown"
                    )
                else:
                    raise e
        else:
            await query.message.reply_text("❌ Erro ao baixar o PDF.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help - Ajuda."""
    await start(update, context)


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /desinscrever - Remove usuário das notificações automáticas."""
    chat_id = update.effective_chat.id
    
    if diario_bot.remove_subscriber(chat_id):
        await update.message.reply_text(
            "✅ Você foi removido das notificações automáticas.\n\n"
            "Use /start para se inscrever novamente."
        )
    else:
        await update.message.reply_text(
            "ℹ️ Você não está inscrito nas notificações automáticas.\n\n"
            "Use /start para se inscrever."
        )


async def send_notification_to_all(bot: Bot, message: str, parse_mode: str = "Markdown") -> int:
    """Envia notificação para todos os usuários inscritos."""
    if not diario_bot.subscribers:
        logger.warning("Nenhum usuário inscrito. Notificação não enviada.")
        return 0
    
    sent_count = 0
    failed_chats = []
    
    for chat_id in diario_bot.subscribers.copy():
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Erro ao enviar para {chat_id}: {e}")
            # Remove usuários que bloquearam o bot ou não existem mais
            if "bot was blocked" in str(e).lower() or "chat not found" in str(e).lower():
                failed_chats.append(chat_id)
    
    # Remove chats inválidos
    for chat_id in failed_chats:
        diario_bot.remove_subscriber(chat_id)
    
    logger.info(f"Notificação enviada para {sent_count}/{len(diario_bot.subscribers)} usuários")
    return sent_count


async def send_document_to_all(bot: Bot, document: BytesIO, filename: str, caption: str) -> int:
    """Envia documento para todos os usuários inscritos."""
    if not diario_bot.subscribers:
        logger.warning("Nenhum usuário inscrito. Documento não enviado.")
        return 0
    
    sent_count = 0
    failed_chats = []
    
    for chat_id in diario_bot.subscribers.copy():
        try:
            document.seek(0)
            await bot.send_document(
                chat_id=chat_id,
                document=document,
                filename=filename,
                caption=caption
            )
            sent_count += 1
        except NetworkError as e:
            if "Request Entity Too Large" in str(e):
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ *Arquivo muito grande para enviar*\n\n{caption}\n\nO PDF excede o limite de 50MB do Telegram.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            else:
                logger.error(f"Erro ao enviar documento para {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Erro ao enviar documento para {chat_id}: {e}")
            if "bot was blocked" in str(e).lower() or "chat not found" in str(e).lower():
                failed_chats.append(chat_id)
    
    # Remove chats inválidos
    for chat_id in failed_chats:
        diario_bot.remove_subscriber(chat_id)
    
    logger.info(f"Documento enviado para {sent_count}/{len(diario_bot.subscribers)} usuários")
    return sent_count


# Funções de compatibilidade (para manter código existente funcionando)
async def send_notification(bot: Bot, message: str, parse_mode: str = "Markdown") -> bool:
    """Envia notificação para todos os usuários inscritos."""
    count = await send_notification_to_all(bot, message, parse_mode)
    return count > 0


async def send_document_notification(bot: Bot, document: BytesIO, filename: str, caption: str) -> bool:
    """Envia documento para todos os usuários inscritos."""
    count = await send_document_to_all(bot, document, filename, caption)
    return count > 0


async def startup_routine(application: Application) -> None:
    """Rotina executada ao iniciar o bot: baixa PDF e faz pesquisa automática."""
    bot = application.bot
    
    logger.info("=" * 50)
    logger.info("INICIANDO ROTINA DE INICIALIZAÇÃO")
    logger.info("=" * 50)
    
    # Notifica que está iniciando
    await send_notification(
        bot,
        "🚀 *Bot iniciado!*\n\n⏳ Baixando PDF da edição atual..."
    )
    
    # Obtém informações da edição atual
    info = diario_bot.get_current_edition_info()
    
    if not info["success"]:
        await send_notification(
            bot,
            f"❌ *Erro ao obter edição:* {info['error']}"
        )
        return
    
    # Baixa o PDF
    logger.info(f"Baixando edição {info['edition_number']}...")
    pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
    
    if not pdf_bytes:
        await send_notification(
            bot,
            "❌ *Erro ao baixar o PDF.*\nTente novamente mais tarde."
        )
        return
    
    # Notifica que baixou com sucesso
    await send_notification(
        bot,
        f"✅ *PDF baixado com sucesso!*\n\n"
        f"📰 Edição: *{info['edition_number']}*\n"
        f"📅 Data: {info['edition_date']}\n\n"
        f"🔍 Iniciando pesquisa automática das palavras-chave padrão..."
    )
    
    # Faz pesquisa automática com palavras-chave padrão
    logger.info(f"Pesquisando palavras-chave padrão: {DEFAULT_KEYWORDS}")
    
    search_results = diario_bot.search_keywords_in_pdf(pdf_bytes, DEFAULT_KEYWORDS)
    
    if not search_results["success"]:
        await send_notification(
            bot,
            f"❌ *Erro na pesquisa:* {search_results['error']}"
        )
        return
    
    # Monta mensagem com resultados
    results = search_results["results"]
    found_keywords = []
    message_parts = ["📊 *Resultado da pesquisa automática:*\n"]
    message_parts.append(f"📰 Edição {info['edition_number']} ({info['edition_date']})\n")
    
    for keyword, data in results.items():
        count = data["count"]
        pages = data["pages"]
        
        if count > 0:
            found_keywords.append(keyword)
            pages_str = ", ".join(map(str, pages[:10]))
            if len(pages) > 10:
                pages_str += f"... (+{len(pages) - 10})"
            message_parts.append(f"\n✅ *{keyword}*")
            message_parts.append(f"   📍 {count} ocorrência(s) em {len(pages)} página(s)")
            message_parts.append(f"   📄 Páginas: {pages_str}")
        else:
            message_parts.append(f"\n❌ *{keyword}* - não encontrado")
    
    # Envia resultado da pesquisa
    await send_notification(bot, "\n".join(message_parts))
    
    # Se encontrou palavras, gera PDF destacado
    if found_keywords:
        await send_notification(
            bot,
            f"\n✨ Gerando PDF com {len(found_keywords)} termo(s) destacado(s)..."
        )
        
        highlighted_pdf = diario_bot.highlight_keywords_in_pdf(
            pdf_bytes,
            DEFAULT_KEYWORDS,
            results
        )
        
        if highlighted_pdf:
            pages_found = set()
            for kw, data in results.items():
                pages_found.update(data.get("pages", []))
            
            await send_document_notification(
                bot,
                highlighted_pdf,
                f"DM_{info['edition_number']}_DESTACADO.pdf",
                f"📰 Edição {info['edition_number']}\n"
                f"📄 {len(pages_found)} página(s) com palavras encontradas\n"
                f"🔍 Termos: {', '.join(found_keywords)}"
            )
    
    await send_notification(
        bot,
        "\n✅ *Bot pronto para uso!*\n\n"
        "Use /pesquisar para buscar suas palavras-chave\n"
        "Use /buscar <termo> para busca rápida\n\n"
        "⏰ Próxima pesquisa automática: *12:00*"
    )
    
    logger.info("Rotina de inicialização concluída!")


async def scheduled_search(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pesquisa agendada às 12h - limpa cache e baixa nova edição."""
    bot = context.bot
    
    logger.info("=" * 50)
    logger.info("INICIANDO PESQUISA AGENDADA (12:00)")
    logger.info("=" * 50)
    
    # Notifica início
    await send_notification(
        bot,
        "⏰ *Pesquisa agendada das 12:00*\n\n"
        "🗑️ Limpando cache antigo...\n"
        "⏳ Verificando nova edição..."
    )
    
    # Limpa cache
    deleted = diario_bot.clear_cache()
    logger.info(f"Cache limpo: {deleted} arquivo(s) removido(s)")
    
    # Obtém informações da edição atual (vai buscar a mais recente)
    info = diario_bot.get_current_edition_info()
    
    if not info["success"]:
        await send_notification(
            bot,
            f"❌ *Erro ao obter edição:* {info['error']}"
        )
        return
    
    await send_notification(
        bot,
        f"📰 *Edição encontrada:* {info['edition_number']}\n"
        f"📅 Data: {info['edition_date']}\n\n"
        f"⏳ Baixando PDF..."
    )
    
    # Baixa o PDF
    pdf_bytes = diario_bot.download_pdf(info["pdf_url"], info["edition_number"])
    
    if not pdf_bytes:
        await send_notification(
            bot,
            "❌ *Erro ao baixar o PDF.*"
        )
        return
    
    await send_notification(
        bot,
        "✅ *PDF baixado!*\n\n🔍 Pesquisando palavras-chave..."
    )
    
    # Faz pesquisa
    search_results = diario_bot.search_keywords_in_pdf(pdf_bytes, DEFAULT_KEYWORDS)
    
    if not search_results["success"]:
        await send_notification(
            bot,
            f"❌ *Erro na pesquisa:* {search_results['error']}"
        )
        return
    
    # Monta mensagem com resultados
    results = search_results["results"]
    found_keywords = []
    message_parts = ["📊 *Resultado da pesquisa das 12:00:*\n"]
    message_parts.append(f"📰 Edição {info['edition_number']} ({info['edition_date']})\n")
    
    for keyword, data in results.items():
        count = data["count"]
        pages = data["pages"]
        
        if count > 0:
            found_keywords.append(keyword)
            pages_str = ", ".join(map(str, pages[:10]))
            if len(pages) > 10:
                pages_str += f"... (+{len(pages) - 10})"
            message_parts.append(f"\n✅ *{keyword}*")
            message_parts.append(f"   📍 {count} ocorrência(s) em {len(pages)} página(s)")
            message_parts.append(f"   📄 Páginas: {pages_str}")
        else:
            message_parts.append(f"\n❌ *{keyword}* - não encontrado")
    
    await send_notification(bot, "\n".join(message_parts))
    
    # Se encontrou palavras, gera PDF destacado
    if found_keywords:
        await send_notification(
            bot,
            f"\n✨ Gerando PDF com {len(found_keywords)} termo(s) destacado(s)..."
        )
        
        highlighted_pdf = diario_bot.highlight_keywords_in_pdf(
            pdf_bytes,
            DEFAULT_KEYWORDS,
            results
        )
        
        if highlighted_pdf:
            pages_found = set()
            for kw, data in results.items():
                pages_found.update(data.get("pages", []))
            
            await send_document_notification(
                bot,
                highlighted_pdf,
                f"DM_{info['edition_number']}_DESTACADO.pdf",
                f"📰 Edição {info['edition_number']}\n"
                f"📄 {len(pages_found)} página(s) com palavras encontradas\n"
                f"🔍 Termos: {', '.join(found_keywords)}"
            )
    else:
        await send_notification(
            bot,
            "\n📭 Nenhuma das palavras-chave foi encontrada nesta edição."
        )
    
    await send_notification(
        bot,
        "\n✅ *Pesquisa agendada concluída!*\n\n"
        "⏰ Próxima pesquisa: amanhã às *12:00*"
    )
    
    logger.info("Pesquisa agendada concluída!")


def main() -> None:
    """Função principal que inicia o bot."""
    if not BOT_TOKEN:
        print("❌ ERRO: Token do bot não configurado!")
        print("Crie um arquivo .env com: TELEGRAM_BOT_TOKEN=seu_token_aqui")
        print("\nPara obter um token:")
        print("1. Abra o Telegram e procure por @BotFather")
        print("2. Envie /newbot e siga as instruções")
        print("3. Copie o token gerado")
        return
    
    # Cria a aplicação
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Adiciona handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("edicao", get_edition))
    application.add_handler(CommandHandler("baixar", download_edition))
    application.add_handler(CommandHandler("palavras", list_keywords))
    application.add_handler(CommandHandler("adicionar", add_keyword))
    application.add_handler(CommandHandler("remover", remove_keyword))
    application.add_handler(CommandHandler("limpar", clear_keywords))
    application.add_handler(CommandHandler("cache", clear_cache))
    application.add_handler(CommandHandler("resetar", reset_keywords))
    application.add_handler(CommandHandler("pesquisar", search_keywords))
    application.add_handler(CommandHandler("buscar", quick_search))
    application.add_handler(CommandHandler("desinscrever", unsubscribe))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Agenda pesquisa diária às 12:00
    job_queue = application.job_queue
    job_queue.run_daily(
        scheduled_search,
        time=time(hour=12, minute=0, second=0),
        name="pesquisa_diaria"
    )
    logger.info("⏰ Pesquisa diária agendada para 12:00")
    
    # Adiciona rotina de inicialização
    application.post_init = startup_routine
    
    # Inicia o bot
    print("🤖 Bot iniciado! Pressione Ctrl+C para parar.")
    print(f"📋 Palavras-chave padrão: {', '.join(DEFAULT_KEYWORDS)}")
    print(f"👥 Usuários inscritos: {len(diario_bot.subscribers)}")
    print("⏰ Pesquisa automática agendada para: 12:00")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
