# Cac lenh thuong dung (Windows PowerShell).
#   .\tasks.ps1 install | lint | test | backfill | snapshot | fundamentals | backtest | scan | bot
param([Parameter(Position=0)][string]$Task = "help")

$env:PYTHONPATH = "$PSScriptRoot\src"

switch ($Task) {
    "install"      { pip install -r requirements.txt }
    "lint"         { ruff check src tests scripts }
    "test"         { pytest -q }
    "backfill"     { python scripts/backfill_data.py }
    "snapshot"     { python scripts/build_snapshot.py }
    "fundamentals" { python scripts/backfill_fundamentals.py }
    "backtest"     { python scripts/run_backtest.py }
    "scan"         { python scripts/run_scan.py }
    "bot"          { python -m bot_phan_tich.bot.main }
    default        {
        Write-Host "Cac tac vu: install, lint, test, backfill, snapshot, fundamentals, backtest, scan, bot"
        Write-Host "Vi du: .\tasks.ps1 test"
    }
}
