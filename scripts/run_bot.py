"""Diem khoi chay bot khong can PYTHONPATH hay `pip install -e .` - dung cho
cac file .bat tren Windows (scripts/windows/bot.ps1).

Tu them src/ vao duong dan va chuyen thu muc lam viec ve goc repo (de .env,
data/, logs/bot.log dung cho), vi tien trinh chay ngam duoc tao qua WMI khong
ke thua bien moi truong cua cua so da khoi dong no.

    python scripts/run_bot.py     # tuong duong python -m bot_phan_tich.bot.main
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

from bot_phan_tich.bot.main import main  # noqa: E402

if __name__ == "__main__":
    main()
