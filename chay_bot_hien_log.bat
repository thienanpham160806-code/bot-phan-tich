@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================================
echo   KHOI DONG BOT (HIEN THI CUA SO LOG DE THEO DOI)
echo ========================================================
python -m bot_phan_tich.bot.main
pause
