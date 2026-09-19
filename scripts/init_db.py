"""Tao cac bang SQLite can thiet."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot_phan_tich.data.cache import init_db  # noqa: E402
from bot_phan_tich.logging_conf import setup_logging  # noqa: E402

if __name__ == "__main__":
    setup_logging()
    init_db()
    print("Da khoi tao cơ sở dữ liệu.")
