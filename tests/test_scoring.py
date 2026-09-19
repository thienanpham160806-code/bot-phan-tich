import numpy as np
import pandas as pd

from bot_phan_tich.analysis.scoring import (
    ACTION_ACCUMULATE,
    ACTION_BUY,
    ACTION_REDUCE,
    ACTION_SELL,
    ACTION_WATCH,
    _map_action,
    recommend,
    score_ichimoku,
    score_macd,
    score_rsi,
)
from bot_phan_tich.config import get_settings


def _frame(close: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    n = len(close)
    return pd.DataFrame(
        {
            "close": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": volume if volume is not None else np.full(n, 100_000.0),
        }
    )


def test_score_functions_stay_within_bounds():
    states = [
        {"above_zero": True, "cross": "golden", "bars_since_cross": 0, "hist_slope": 5.0},
        {"above_zero": False, "cross": "death", "bars_since_cross": 30, "hist_slope": -5.0},
        {"above_zero": None, "cross": None, "bars_since_cross": None, "hist_slope": None},
    ]
    for state in states:
        assert -100.0 <= score_macd(state) <= 100.0

    rsi_states = [
        {"value": 95.0, "zone": "qua_mua", "upper": 80.0, "lower": 20.0, "slope": 10.0},
        {"value": 5.0, "zone": "qua_ban", "upper": 80.0, "lower": 20.0, "slope": -10.0},
        {"value": None, "zone": None, "upper": None, "lower": None, "slope": None},
    ]
    for state in rsi_states:
        assert -100.0 <= score_rsi(state) <= 100.0

    ichi_states = [
        {"price_vs_kumo": "tren_may", "tk_cross": ("golden", 0, "manh"),
         "chikou_free": True, "kumo_twist": False, "kumo_thickness": 2.0},
        {"price_vs_kumo": "duoi_may", "tk_cross": ("death", 0, "yeu"),
         "chikou_free": False, "kumo_twist": True, "kumo_thickness": 2.0},
        {"price_vs_kumo": None, "tk_cross": (None, None, None),
         "chikou_free": None, "kumo_twist": None, "kumo_thickness": None},
    ]
    for state in ichi_states:
        assert -100.0 <= score_ichimoku(state) <= 100.0


def test_map_action_boundaries_match_settings_thresholds():
    settings = get_settings()
    assert _map_action(60.0, settings) == ACTION_BUY
    assert _map_action(59.9, settings) == ACTION_ACCUMULATE
    assert _map_action(20.0, settings) == ACTION_ACCUMULATE
    assert _map_action(19.9, settings) == ACTION_WATCH
    assert _map_action(-20.0, settings) == ACTION_WATCH
    assert _map_action(-20.1, settings) == ACTION_REDUCE
    assert _map_action(-60.0, settings) == ACTION_REDUCE
    assert _map_action(-60.1, settings) == ACTION_SELL


def test_ichimoku_veto_blocks_buy_when_price_below_kumo():
    # Dinh cao, giam sau, roi phuc hoi mot phan: MACD/RSI da chuyen sang tang
    # manh nhung gia van con duoi may Kumo (may con tre theo du lieu 26 phien
    # truoc, khi gia con o vung cao).
    high = np.linspace(100, 200, 60)
    decline = np.linspace(200, 60, 80)
    rally = np.linspace(60, 80, 20)
    frame = _frame(np.concatenate([high, decline, rally]))

    # Trong so ep het vao MACD/RSI de neu KHONG co quyen phu quyet, diem tong
    # se >= nguong MUA.
    rec = recommend(frame, "TEST", weights={"macd": 1.0, "rsi": 1.0, "ichimoku": 0.0})

    assert rec.vetoed_by_kumo is True
    assert rec.total_score >= 60.0  # xac nhan tinh huong nay THUC SU se la MUA neu khong bi chan
    assert rec.action != ACTION_BUY


def test_recommend_returns_consistent_price_levels_on_uptrend():
    close = np.linspace(50, 150, 250)
    frame = _frame(close)
    rec = recommend(frame, "abc")

    assert rec.symbol == "ABC"
    assert rec.stop_loss < rec.close
    assert rec.target > rec.close
    assert rec.entry_low <= rec.entry_high
    assert rec.risk_reward is None or rec.risk_reward > 0
    assert len(rec.reasons) == 3


def test_low_volume_downgrades_confidence():
    close = np.linspace(50, 150, 250)
    volume = np.full(250, 100_000.0)
    volume[-1] = 1_000.0  # phien cuoi rat thap so voi TB20
    frame = _frame(close, volume)

    rec = recommend(frame, "abc")
    assert rec.confidence != "cao"
