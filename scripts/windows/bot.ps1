# Quan ly bot chay ngam tren Windows: start | stop | status.
# Duoc goi tu chay_bot_an.bat, tat_bot.bat (thu muc goc repo).
#
#  - Dung pythonw.exe trong .venv cua repo (neu co), khong thi pythonw tren PATH.
#  - Khoi dong qua Win32_Process.Create (WMI): tien trinh do dich vu WMI tao,
#    KHONG thuoc cay tien trinh / job cua terminal hay IDE -> dong cua so
#    terminal, VS Code, Antigravity... bot van chay.
#  - Tien trinh WMI khong ke thua bien moi truong, nen chay qua
#    scripts/run_bot.py (tu them src/ vao duong dan, tu chuyen ve goc repo).
#  - Nhan dien tien trinh bot theo DONG LENH, khong giet nham pythonw khac.
#  - Log: logs/bot.log.
param(
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$LogFile = Join-Path $Root 'logs\bot.log'
$Launcher = Join-Path $Root 'scripts\run_bot.py'

function Get-BotProcess {
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like '*run_bot.py*' -or
                $_.CommandLine -like '*bot_phan_tich.bot.main*'
            )
        }
}

function Get-Pythonw {
    $venv = Join-Path $Root '.venv\Scripts\pythonw.exe'
    if (Test-Path $venv) { return $venv }
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "[CANH BAO] Khong thay .venv\Scripts\pythonw.exe, dung $($cmd.Source)"
        return $cmd.Source
    }
    throw 'Khong tim thay pythonw.exe (trong .venv cua repo hoac tren PATH).'
}

function Read-LogFrom([long]$Offset) {
    if (-not (Test-Path $LogFile)) { return '' }
    # FileShare ReadWrite: bot dang giu file log de ghi tiep.
    $stream = [System.IO.File]::Open($LogFile, 'Open', 'Read', 'ReadWrite')
    try {
        if ($Offset -gt $stream.Length) { $Offset = 0 }
        [void]$stream.Seek($Offset, 'Begin')
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        return $reader.ReadToEnd()
    } finally {
        $stream.Dispose()
    }
}

function Show-Status {
    $procs = @(Get-BotProcess)
    if ($procs.Count -eq 0) {
        Write-Host '[TRANG THAI] Bot KHONG chay.'
        return
    }
    foreach ($p in $procs) {
        $mb = [math]::Round((Get-Process -Id $p.ProcessId).WorkingSet64 / 1MB)
        Write-Host "[TRANG THAI] Bot DANG CHAY - PID $($p.ProcessId), $($p.Name), RAM $mb MB"
    }
    Write-Host "Log: $LogFile"
}

switch ($Action) {
    'status' {
        Show-Status
        # Ma thoat 3 = bot dang chay (chay_bot_hien_log.bat dung de tranh chay trung).
        if (@(Get-BotProcess).Count -gt 0) { exit 3 }
    }

    'stop' {
        $procs = @(Get-BotProcess)
        if ($procs.Count -eq 0) {
            Write-Host '[THONG BAO] Khong co tien trinh bot nao dang chay.'
            exit 0
        }
        foreach ($p in $procs) {
            Stop-Process -Id $p.ProcessId -Force
            Write-Host "[THANH CONG] Da dung bot (PID $($p.ProcessId))."
        }
    }

    'start' {
        if (@(Get-BotProcess).Count -gt 0) {
            Write-Host '[THONG BAO] Bot da dang chay. Muon khoi dong lai thi chay tat_bot.bat truoc.'
            Show-Status
            exit 0
        }
        $pythonw = Get-Pythonw
        New-Item -ItemType Directory -Force (Split-Path $LogFile) | Out-Null
        $offset = 0
        if (Test-Path $LogFile) { $offset = (Get-Item $LogFile).Length }

        $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine      = "`"$pythonw`" `"$Launcher`""
            CurrentDirectory = $Root
        }
        if ($result.ReturnValue -ne 0) {
            throw "Khong tao duoc tien trinh (Win32_Process.Create tra ve $($result.ReturnValue))."
        }
        $botPid = $result.ProcessId
        Write-Host "Dang khoi dong bot (PID $botPid)..."

        # Cho toi 30 giay: thanh cong khi log bao da ket noi Telegram; that
        # bai neu tien trinh chet (vd thieu TELEGRAM_BOT_TOKEN, loi import).
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            $alive = Get-Process -Id $botPid -ErrorAction SilentlyContinue
            $newLog = Read-LogFrom $offset
            if (-not $alive) {
                Write-Host '[LOI] Bot da thoat ngay sau khi khoi dong. Log moi nhat:'
                Write-Host ($newLog.Trim().Split("`n") | Select-Object -Last 15 | Out-String)
                exit 1
            }
            if ($newLog -match 'Run polling') {
                Write-Host "[THANH CONG] Bot da chay ngam va ket noi Telegram (PID $botPid)."
                Write-Host 'Co the dong cua so nay, terminal hay IDE - bot van chay.'
                Write-Host "Log: $LogFile"
                exit 0
            }
        }
        Write-Host "[CANH BAO] Bot van chay (PID $botPid) nhung chua thay log ket noi Telegram"
        Write-Host "sau 30 giay - xem $LogFile hoac go /trangthai tren Telegram."
    }
}
