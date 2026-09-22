@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================================
echo   KHOI DONG BOT CHAY NGAM (KHONG HIEN CUA SO)
echo ========================================================

:: Kiem tra neu bot dang chay thi khong khoi dong trung lap
tasklist /fi "imagename eq pythonw.exe" | findstr /i "pythonw.exe" > nul
if %errorlevel% equ 0 (
    echo [THONG BAO] Bot da dang chay ngam trong he thong!
    echo Neu muon khoi dong lai, hay chay file 'tat_bot.bat' truoc.
    pause
    exit /b 0
)

:: Khoi dong ngam bang pythonw
start "" pythonw -m bot_phan_tich.bot.main

echo [THANH CONG] Bot da duoc khoi dong chay ngam!
echo Ban co the tat hoan toan VS Code / Antigravity ma bot van hoat dong.
echo Xem file log tai: logs\bot.log hoac mo Telegram kiem tra.
