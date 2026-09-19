"""Diem dung lo, chot loi va dung lo dong."""
from __future__ import annotations

import pandas as pd

from ..config import get_settings


def initial_stop(entry: float, atr: float, pattern_low: float | None = None,
                 k_sl: float | None = None) -> float:
    """Diem dung ban dau: lay muc GAN HON giua (entry - k*ATR) va day mau hinh."""
    k_sl = k_sl or get_settings().get("signals.stop_loss_atr", 1.5)
    atr_stop = entry - k_sl * atr
    if pattern_low is None:
        return atr_stop
    return max(atr_stop, pattern_low * 0.99)


def take_profit(entry: float, atr: float, k_tp: float | None = None) -> float:
    k_tp = k_tp or get_settings().get("signals.take_profit_atr", 3.0)
    return entry + k_tp * atr


def chandelier_exit(frame: pd.DataFrame, since_index: int, atr_mult: float | None = None,
                    atr_col: str = "atr14") -> float | None:
    """Dung lo dong: dinh cao nhat ke tu khi vao lenh, tru atr_mult * ATR."""
    atr_mult = atr_mult or get_settings().get("risk.chandelier_atr_mult", 3.0)
    window = frame.iloc[since_index:]
    if window.empty:
        return None
    atr_value = window[atr_col].iloc[-1]
    if pd.isna(atr_value):
        return None
    return float(window["high"].max() - atr_mult * float(atr_value))


def partial_exit_price(entry: float, stop_loss: float, r_target: float | None = None) -> float:
    """Gia ban mot phan vi the tai muc r_target lan rui ro (mac dinh 2R)."""
    r_target = r_target or get_settings().get("risk.partial_take_profit_r", 2.0)
    return entry + r_target * (entry - stop_loss)
