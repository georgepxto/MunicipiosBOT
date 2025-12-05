@echo off
CHCP 65001 >nul
title Bot Diário Oficial dos Municípios
echo ============================================
echo   Bot Diário Oficial dos Municípios
echo ============================================
echo.
echo Iniciando bot...
echo.
echo Para parar, pressione Ctrl+C
echo.
cd /d "%~dp0"
python bot.py
pause
