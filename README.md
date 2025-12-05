# 🏛️ Bot do Diário Oficial dos Municípios

Um bot do Telegram que busca e destaca termos no Diário Oficial dos Municípios do Piauí automaticamente.

## 📌 O que faz?

- ✅ **Pesquisa automática** - Busca suas palavras-chave diariamente às 12:00
- ✅ **Notificações** - Envia resultados diretamente no Telegram
- ✅ **PDF destacado** - Destaca os termos encontrados em cores diferentes
- ✅ **Pesquisa sob demanda** - Busque a qualquer hora com comandos
- ✅ **Palavras-chave personalizadas** - Cada usuário pode ter suas próprias palavras

## 🚀 Como usar (Primeira vez)

### 1️⃣ **Instalar dependências**

Abra a pasta do bot e **clique duas vezes** em:

```
instalar_dependencias.bat
```

> ℹ️ Isso vai instalar o Python e todas as bibliotecas necessárias.
> Vai demorar alguns minutos. Deixe terminar até aparecer "Pressione uma tecla".

### 2️⃣ **Iniciar o bot**

Depois de instalar, **clique duas vezes** em:

```
municipios_bot.bat
```

> ✅ Uma janela vai abrir com o bot rodando.
> Deixe aberta o tempo que quiser usar o bot.

### 3️⃣ **No Telegram**

1. Abra o Telegram
2. Procure pelo bot (nome do seu bot)
3. Envie `/start`
4. Pronto! Você está inscrito e receberá notificações automáticas

## 📱 Comandos do Telegram

| Comando                | O que faz                                  |
| ---------------------- | ------------------------------------------ |
| `/start`               | Inicia o bot e se inscreve em notificações |
| `/pesquisar`           | Busca suas palavras-chave agora            |
| `/buscar <termo>`      | Busca um termo específico                  |
| `/edicao`              | Mostra a edição atual do Diário            |
| `/baixar`              | Baixa o PDF completo                       |
| `/palavras`            | Lista suas palavras-chave                  |
| `/adicionar <palavra>` | Adiciona uma nova palavra-chave            |
| `/remover <palavra>`   | Remove uma palavra-chave                   |
| `/resetar`             | Volta às palavras-chave padrão             |
| `/desinscrever`        | Cancela notificações automáticas           |

## ⚙️ Configuração

### Palavras-chave padrão

O bot vem com essas palavras-chave padrão:

- Convita
- mg gestão ambiental
- Bioparque Zoobotânico
- r m estrutura e pavimentação
- Luiz Francisco do Rego Monteiro
- Lumig
- Molla

Você pode mudar usando `/adicionar` e `/remover`.

### Token do bot (`.env`)

O arquivo `.env` contém o token secreto do bot. **Não compartilhe!**

Se precisar passar para outro PC, copie também o arquivo `.env` junto.

## 💾 Como passar para outro PC

1. **Copie a pasta completa** do bot
2. **Execute** `instalar_dependencias.bat` (primeira vez apenas)
3. **Execute** `municipios_bot.bat` para rodar

Pronto! Funciona igual no outro PC.

## 📂 Estrutura de arquivos

```
botmunicipios/
├── bot.py                      # Código do bot
├── .env                        # Token (SEGREDO!)
├── requirements.txt            # Dependências
├── municipios_bot.bat          # Clique para iniciar
├── instalar_dependencias.bat   # Clique na primeira vez
├── README.md                   # Este arquivo
├── subscribers.json            # Usuários (criado automaticamente)
└── cache/                      # PDFs (criado automaticamente)
```

## 🔔 Como funciona a pesquisa automática?

**Todos os dias às 12:00:**

1. Bot limpa o PDF antigo
2. Baixa edição mais recente
3. Busca todas as palavras-chave
4. Envia resultados para todos inscritos
5. Anexa PDF com termos destacados

## 🆘 Problemas comuns

### "Bot iniciado!" mas nada aparece no Telegram

Espere um pouco. Está buscando a edição e pode demorar alguns segundos.

### "Python não encontrado"

Execute `instalar_dependencias.bat` novamente.

### O bot parou de responder

Feche a janela (Ctrl+C) e execute `municipios_bot.bat` novamente.

### PDF muito grande para enviar

Use `/pesquisar` ou `/buscar`. Enviam apenas as páginas com seus termos!

## 🆘 Como obter o Token do Bot?

1. Abra Telegram e procure: **@BotFather**
2. Envie: `/newbot`
3. Escolha um nome para seu bot (ex: botmunicipios)
4. Copie o token que aparece
5. Edite `.env` e troque `seu_token` pelo token copiado

## ℹ️ Informações técnicas

- **Linguagem:** Python 3.8+
- **Dependências:** python-telegram-bot, requests, PyMuPDF, python-dotenv

---

**Dúvidas?** Envie `/help` no Telegram ou reinicie com `municipios_bot.bat`.
