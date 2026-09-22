"""Sinh tin hieu MUA lich su tu analysis/scoring.py de dua vao backtest/engine.py.

Giai quyet van de: backtest/engine.py:run() chi biet CHAY tren mot DataFrame
tin hieu (symbol, time, stop_loss, target) co san - no khong tu sinh tin
hieu. Tin hieu MUA duoc sinh bang cach quet lai analysis/scoring.recommend()
tren TUNG PHIEN trong qua khu.

Chong nhin truoc tuong lai (look-ahead bias): tai moi buoc quet o phien i,
CHI dua vao frame.iloc[: i + 1] - giong het du lieu ma nguoi giao dich thuc
te co duoc tai thoi diem do, khong dung bat ky thong tin cua cac phien sau.
"""
from __future__ import annotations

import pandas as pd

from ..analysis.scoring import ACTION_BUY, recommend
from ..logging_conf import get_logger

log = get_logger(__name__)

_MIN_BARS = 60
SIGNAL_COLUMNS = ["symbol", "time", "stop_loss", "target"]


def generate_buy_signals(frame: pd.DataFrame, symbol: str, min_gap: int = 5) -> pd.DataFrame:
    """Quet qua khu cua mot ma, tra ve moi phien ma recommend() cho khuyen nghi MUA.

    `min_gap`: so phien toi thieu giua hai tin hieu lien tiep cho CUNG mot ma
    - tranh sinh hang chuc tin hieu trung lap cho cung mot nhip tang gia.
    Tra ve DataFrame dung dinh dang backtest/engine.py:run() can (cot
    SIGNAL_COLUMNS), rong neu khong tim thay tin hieu nao hoac du lieu qua ngan.
    """
    if len(frame) < _MIN_BARS:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)

    rows: list[dict] = []
    last_hit = -min_gap
    for i in range(_MIN_BARS, len(frame)):
        if i - last_hit < min_gap:
            continue
        window = frame.iloc[: i + 1]
        try:
            rec = recommend(window, symbol)
        except Exception as exc:
            log.debug("generate_buy_signals(%s) loi tai phien %d: %s", symbol, i, exc)
            continue
        if rec.action == ACTION_BUY:
            rows.append(
                {
                    "symbol": symbol,
                    "time": frame["time"].iloc[i],
                    "stop_loss": rec.stop_loss,
                    "target": rec.target,
                }
            )
            last_hit = i

    return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)


def generate_signals_for_universe(
    price_frames: dict[str, pd.DataFrame], min_gap: int = 5
) -> pd.DataFrame:
    """Ap generate_buy_signals() cho nhieu ma, gop thanh mot DataFrame tin hieu
    duy nhat - dau vao truc tiep cho backtest/engine.py:run() va walk_forward.py.
    """
    frames = []
    for symbol, frame in price_frames.items():
        try:
            frames.append(generate_buy_signals(frame, symbol, min_gap))
        except Exception as exc:
            log.warning("generate_signals_for_universe: bo qua %s do loi: %s", symbol, exc)
    if not frames:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    return pd.concat(frames, ignore_index=True)
