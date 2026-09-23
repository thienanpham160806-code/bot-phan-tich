@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   KHOI DONG BOT (HIEN CUA SO LOG) - dong cua so nay la bot dung
echo ========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\bot.ps1" status > nul
if errorlevel 3 (
    echo [LOI] Bot dang chay ngam. Chay tat_bot.bat truoc, neu khong se co 2 bot
    echo cung nhan tin nhan va Telegram bao loi xung dot.
    pause
    exit /b 1
)
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" scripts\run_bot.py
pause
