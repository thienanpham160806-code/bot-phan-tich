"""Dung vu tru co phieu du dieu kien tai mot ngay bat ky.

Quan trong cho backtest: vu tru phai duoc dung lai theo dung danh sach cua ngay
do, khong duoc dung danh sach hom nay cho qua khu (thien lech song sot).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ..config import get_settings, get_universe_config
from ..logging_conf import get_logger
from .router import get_router

log = get_logger(__name__)


def liquid_universe(as_of: date | None = None, use_watchlist: bool = False) -> list[str]:
    """Danh sach ma dat nguong thanh khoan va gia tai ngay as_of."""
    if use_watchlist:
        return [s.upper() for s in get_universe_config()["watchlist"]]

    settings = get_settings()
    as_of = as_of or date.today()
    router = get_router()

    exchanges = settings.get("universe.exchanges", ["HOSE", "HNX", "UPCOM"])
    min_volume = settings.get("universe.min_avg_volume_20d", 100_000)
    min_price = settings.get("universe.min_price", 5_000)
    max_price = settings.get("universe.max_price", 300_000)
    min_days = settings.get("universe.min_listed_days", 250)

    listing = router.listing(exchanges)
    symbols = [str(s).upper() for s in listing["symbol"].dropna().unique()]
    log.info("Danh sach niem yet: %d ma", len(symbols))

    keep: list[str] = []
    start = as_of - timedelta(days=int(min_days * 1.6))
    for symbol in symbols:
        try:
            frame = router.ohlcv(symbol, start, as_of)
        except Exception:
            continue
        if len(frame) < min_days:
            continue
        last_close = float(frame["close"].iloc[-1])
        avg_volume = float(frame["volume"].tail(20).mean())
        if min_price <= last_close <= max_price and avg_volume >= min_volume:
            keep.append(symbol)

    log.info("Vu tru du dieu kien tai %s: %d ma", as_of, len(keep))
    return keep


def sector_of(symbols: list[str]) -> pd.Series:
    """Anh xa ma -> nganh, dung cho rang buoc ti trong nganh."""
    mapping = get_router().industry_map()
    if mapping.empty:
        return pd.Series({s: "Khac" for s in symbols})
    col = next(
        (c for c in ("industry", "icb_name3", "icb_name2") if c in mapping.columns), None
    )
    if col is None:
        return pd.Series({s: "Khac" for s in symbols})
    table = mapping.set_index(mapping["symbol"].astype(str).str.upper())[col]
    return pd.Series({s: table.get(s, "Khac") for s in symbols})
