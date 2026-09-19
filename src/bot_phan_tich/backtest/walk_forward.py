"""Kiem dinh walk-forward: huan luyen N thang, kiem tra M thang, lan tiep.

Chi bao cao ket qua tren tap kiem tra chua tung dung de hieu chinh tham so.
"""
from __future__ import annotations

import pandas as pd

from ..logging_conf import get_logger
from . import metrics
from .engine import run

log = get_logger(__name__)


def walk_forward(
    price_frames: dict[str, pd.DataFrame],
    signals: pd.DataFrame,
    train_months: int = 24,
    test_months: int = 3,
    initial_capital: float = 100_000_000,
) -> pd.DataFrame:
    """Chay backtest tren tung lat thoi gian, tra ve bang chi so theo tung lat."""
    if signals.empty:
        return pd.DataFrame()

    signals = signals.sort_values("time")
    start, end = signals["time"].min(), signals["time"].max()
    cursor = start + pd.DateOffset(months=train_months)
    rows = []

    while cursor < end:
        test_end = cursor + pd.DateOffset(months=test_months)
        window = signals[(signals["time"] >= cursor) & (signals["time"] < test_end)]
        if len(window) >= 3:
            result = run(price_frames, window, initial_capital)
            stats = metrics.summarise(result.equity, result.trades)
            stats["Tu"] = cursor.date()
            stats["Den"] = test_end.date()
            rows.append(stats)
            log.info("Lat %s - %s: %d lenh", cursor.date(), test_end.date(), stats["So lenh"])
        cursor = test_end

    return pd.DataFrame(rows)


def compare_benchmarks(
    result_equity: pd.Series, index_frame: pd.DataFrame
) -> pd.DataFrame:
    """So chien luoc voi mua-nam giu VN-Index tren cung khoang thoi gian."""
    if result_equity.empty or index_frame.empty:
        return pd.DataFrame()

    index = index_frame.set_index("time")["close"]
    index = index.reindex(result_equity.index).ffill().dropna()
    if index.empty:
        return pd.DataFrame()

    buy_hold = index / index.iloc[0] * result_equity.iloc[0]
    return pd.DataFrame(
        {
            "Chien luoc": metrics.summarise(result_equity, pd.DataFrame()),
            "Mua va nam giu VN-Index": metrics.summarise(buy_hold, pd.DataFrame()),
        }
    )
