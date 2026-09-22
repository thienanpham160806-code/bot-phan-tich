@echo off
chcp 65001 > nul
echo ========================================================
echo   DUNG TAT CA CAC TIEN TRINH BOT CHAY NGAM
echo ========================================================

taskkill /f /im pythonw.exe > nul 2>&1
if %errorlevel% equ 0 (
    echo [THANH CONG] Da dung tien trinh bot chay ngam.
) else (
    echo [THONG BAO] Khong co tien trinh bot chay ngam nao dang hoat dong.
)

pause
