"""Do thoi gian va RAM dinh khi dung snapshot - kiem tra co vua may chu 512 MB
(Render goi Free) hay khong truoc khi deploy.

Ghi snapshot ra THU MUC TAM, khong de len data/market/snapshot.parquet that.

Cach chay:
    python scripts/bench_snapshot.py               # toan bo vu tru thanh khoan
    python scripts/bench_snapshot.py --limit 200   # chi 200 ma dau
    python scripts/bench_snapshot.py --workers 4   # thu ThreadPoolExecutor 4 luong
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot_phan_tich.analysis import snapshot as snapshot_mod  # noqa: E402
from bot_phan_tich.data import market_store  # noqa: E402
from bot_phan_tich.data.universe import liquid_universe  # noqa: E402
from bot_phan_tich.logging_conf import setup_logging  # noqa: E402
from bot_phan_tich.sysinfo import current_rss_mb, format_mb, peak_rss_mb  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Chi dung N ma dau (0 = tat ca)")
    parser.add_argument("--workers", type=int, default=None, help="So luong (mac dinh: config)")
    args = parser.parse_args()

    setup_logging()
    baseline = current_rss_mb()

    if market_store.load_ohlcv(columns=["symbol"]).empty:
        print("Kho gia rong - chay `python scripts/backfill_data.py` truoc.")
        return

    out_path = Path(tempfile.mkdtemp()) / "snapshot_bench.parquet"
    snapshot_mod.snapshot_path = lambda: out_path

    symbols = liquid_universe()
    if args.limit:
        symbols = symbols[: args.limit]

    started = time.time()
    frame = snapshot_mod.build_snapshot(symbols, max_workers=args.workers)
    elapsed = time.time() - started
    per_symbol_ms = elapsed / max(len(symbols), 1) * 1000

    print("\n" + "=" * 55)
    print(f"Ma dau vao:          {len(symbols)}")
    print(f"Ma co ket qua:       {len(frame)}")
    print(f"Thoi gian:           {elapsed:.1f}s ({per_symbol_ms:.1f} ms/ma)")
    print(f"RAM truoc khi chay:  {format_mb(baseline)}")
    print(f"RAM hien tai:        {format_mb(current_rss_mb())}")
    print(f"RAM dinh:            {format_mb(peak_rss_mb())}")
    print("=" * 55)
    print(f"Snapshot thu: {out_path}")


if __name__ == "__main__":
    main()
