"""Dung vu tru co phieu du dieu kien - tinh HOAN TOAN bang pandas tren kho.

Truoc day ham nay goi router.ohlcv() cho TUNG MA cua ca san (hang tram
request mang, la nguyen nhan chinh khien /loc treo bot). Gio doc mot lan tu
data/market_store.py (kho toan san tren dia, xem scripts/backfill_data.py)
roi loc bang groupby/pandas - KHONG goi mang.

Quan trong cho backtest: vu tru phai duoc dung lai theo dung danh sach cua ngay
do, khong duoc dung danh sach hom nay cho qua khu (thien lech song sot).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..config import get_settings, get_universe_config
from ..logging_conf import get_logger
from . import market_store
from .router import get_router

log = get_logger(__name__)


def liquid_universe(as_of: date | None = None, use_watchlist: bool = False) -> list[str]:
    """Danh sach ma dat nguong thanh khoan va gia tai ngay as_of, tu kho toan san."""
    if use_watchlist:
        return [s.upper() for s in get_universe_config()["watchlist"]]

    settings = get_settings()
    as_of = as_of or date.today()

    exchanges = settings.get("universe.exchanges", ["HOSE", "HNX", "UPCOM"])
    min_volume = settings.get("universe.min_avg_volume_20d", 100_000)
    min_price = settings.get("universe.min_price", 5_000)
    max_price = settings.get("universe.max_price", 300_000)
    min_days = settings.get("universe.min_listed_days", 250)

    frame = market_store.load_ohlcv(columns=["symbol", "time", "close", "volume"])
    if frame.empty:
        log.warning(
            "market_store rong - chua chay scripts/backfill_data.py? "
            "liquid_universe tra ve danh sach rong."
        )
        return []

    frame = frame[frame["time"] <= pd.Timestamp(as_of)]

    symbols_meta = market_store.load_symbols()
    if not symbols_meta.empty and "exchange" in symbols_meta.columns:
        wanted = set(
            symbols_meta.loc[
                symbols_meta["exchange"].astype(str).str.upper().isin(exchanges), "symbol"
            ]
        )
        frame = frame[frame["symbol"].isin(wanted)]

    keep: list[str] = []
    for symbol, group in frame.groupby("symbol", observed=True, sort=False):
        if len(group) < min_days:
            continue
        group = group.sort_values("time")
        last_close = float(group["close"].iloc[-1])
        avg_volume = float(group["volume"].tail(20).mean())
        if min_price <= last_close <= max_price and avg_volume >= min_volume:
            keep.append(str(symbol))

    log.info("Vu tru du dieu kien tai %s: %d ma (tu kho, khong goi mang)", as_of, len(keep))
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
