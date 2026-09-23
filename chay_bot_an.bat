@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   KHOI DONG BOT CHAY NGAM (KHONG HIEN CUA SO)
echo ========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\bot.ps1" start
echo.
echo Kiem tra bot con song: chay kiem_tra_bot.bat, hoac mo Task Manager tim
echo pythonw.exe, hoac go /trangthai tren Telegram. Log: logs\bot.log
rem Chay kem mot tham so bat ky (vd "chay_bot_an.bat tudong" trong thu muc
rem Startup) de khong dung cho bam phim.
if "%~1"=="" pause
