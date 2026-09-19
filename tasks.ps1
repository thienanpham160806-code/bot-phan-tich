# Cac lenh thuong dung (Windows PowerShell).
#   .\tasks.ps1 install | lint | test | backfill | scan | bot
param([Parameter(Position=0)][string]$Task = "help")

$env:PYTHONPATH = "$PSScriptRoot\src"

switch ($Task) {
    "install"  { pip install -r requirements.txt }
    "lint"     { ruff check src tests }
    "test"     { pytest -q }
    "backfill" { python scripts/backfill_data.py --years 3 }
    "scan"     { python scripts/run_scan.py }
    "bot"      { python -m bot_phan_tich.bot.main }
    default    {
        Write-Host "Cac tac vu: install, lint, test, backfill, scan, bot"
        Write-Host "Vi du: .\tasks.ps1 test"
    }
}
