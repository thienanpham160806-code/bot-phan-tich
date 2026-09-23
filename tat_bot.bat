@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   DUNG BOT CHAY NGAM
echo ========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\bot.ps1" stop
pause
