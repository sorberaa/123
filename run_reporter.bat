@echo off
chcp 65001 > nul
title Boss Reporter Bot (@Statictipbot)
cd /d "%~dp0"
echo ==========================================
echo   Запуск бота отчетов для шефа...
echo ==========================================
python bot.py
pause
