"""Tai lich su gia va bao cao tai chinh vao cache cuc bo.

Chay mot lan truoc khi backtest de khong phai goi mang trong vong lap.

    python scripts/backfill_data.py --years 3
    python scripts/backfill_data.py --years 3 --full-universe
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot_phan_tich.config import get_universe_config  # noqa: E402
from bot_phan_tich.data.router import get_router  # noqa: E402
from bot_phan_tich.logging_conf import get_logger, setup_logging  # noqa: E402

log = get_logger("backfill")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--full-universe", action="store_true",
                        help="Tai toan san thay vi chi watchlist")
    parser.add_argument("--skip-financials", action="store_true")
    args = parser.parse_args()

    setup_logging()
    data = get_router()
    config = get_universe_config()

    end = date.today()
    start = end - timedelta(days=365 * args.years + 60)

    if args.full_universe:
        from bot_phan_tich.data.universe import liquid_universe

        symbols = liquid_universe(end)
    else:
        symbols = [s.upper() for s in config["watchlist"]]

    symbols = list(dict.fromkeys(symbols + [config.get("benchmark", "VNINDEX")]))
    log.info("Bat dau tai %d ma tu %s den %s", len(symbols), start, end)

    ok = failed = 0
    for i, symbol in enumerate(symbols, start=1):
        try:
            frame = data.ohlcv(symbol, start, end, force_refresh=True)
            log.info("[%d/%d] %s: %d phien", i, len(symbols), symbol, len(frame))
            if not args.skip_financials and symbol != config.get("benchmark"):
                data.financials(symbol, "quarter")
            ok += 1
        except Exception as exc:
            log.warning("[%d/%d] %s that bai: %s", i, len(symbols), symbol, exc)
            failed += 1

    log.info("Hoan tat: %d thanh cong, %d that bai", ok, failed)


if __name__ == "__main__":
    main()
