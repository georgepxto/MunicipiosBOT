@echo off
CHCP 65001 >nul
title Instalador de Dependências - Bot Diário Oficial
echo ============================================
echo   Instalador de Dependencias
echo   Bot Diário Oficial dos Municípios
echo ============================================
echo.
echo Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ❌ ERRO: Python não encontrado!
    echo.
    echo Por favor, instale Python de https://www.python.org
    echo Marque a opção "Add Python to PATH" durante a instalação
    echo.
    pause
    exit /b 1
)
echo ✅ Python encontrado!
echo.
echo Instalando dependências...
echo (Isso pode demorar alguns minutos)
echo.
pip install -r requirements.txt
if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo ✅ Dependências instaladas com sucesso!
    echo ============================================
    echo.
    echo Agora você pode executar: municipios_bot.bat
    echo.
) else (
    echo.
    echo ❌ Erro ao instalar dependências!
    echo.
    echo Tente executar manualmente:
    echo   pip install -r requirements.txt
    echo.
)
pause
