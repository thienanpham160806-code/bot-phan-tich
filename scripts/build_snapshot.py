"""Tinh khuyen nghi cho toan bo vu tru thanh khoan, ghi ra snapshot.parquet.

Chay tay sau khi backfill_data.py da co du lieu:

    python scripts/backfill_data.py
    python scripts/build_snapshot.py

In thoi gian chay va phan bo khuyen nghi (bao nhieu MUA, TICH LUY...). Ket
qua nam trong data/market/snapshot.parquet, /loc va /tinhieu doc file nay
(analysis/screener.py) - khong tinh lai.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot_phan_tich.analysis.snapshot import build_snapshot, snapshot_path  # noqa: E402
from bot_phan_tich.logging_conf import get_logger, setup_logging  # noqa: E402

log = get_logger("build_snapshot")


def main() -> None:
    setup_logging()
    started = time.time()

    frame = build_snapshot()
    elapsed = time.time() - started

    if frame.empty:
        print(
            "\nKhong tinh duoc snapshot nao - vu tru thanh khoan rong. "
            "Chay `python scripts/backfill_data.py` truoc."
        )
        return

    counts = frame["action"].value_counts()
    print("\n" + "=" * 50)
    print(f"Snapshot: {len(frame)} ma, {elapsed:.1f}s")
    print("=" * 50)
    for action, n in counts.items():
        print(f"  {action:<20} {n:>4} ma")
    print("=" * 50)
    print(f"Da ghi: {snapshot_path()}")


if __name__ == "__main__":
    main()
