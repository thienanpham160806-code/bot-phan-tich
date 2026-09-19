import numpy as np
import pandas as pd

from bot_phan_tich.backtest import metrics
from bot_phan_tich.backtest.engine import run
from bot_phan_tich.backtest.signals import SIGNAL_COLUMNS, generate_buy_signals


def _uptrend_frame(n=200, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 50 * np.exp(np.cumsum(rng.normal(0.003, 0.012, n)))
    return pd.DataFrame(
        {
            "time": pd.date_range("2023-01-02", periods=n, freq="B"),
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": close * (1 + rng.uniform(0.001, 0.01, n)),
            "low": close * (1 - rng.uniform(0.001, 0.01, n)),
            "close": close,
            "volume": rng.integers(100_000, 500_000, n).astype(float),
        }
    )


def test_generate_buy_signals_returns_expected_columns():
    frame = _uptrend_frame()
    signals = generate_buy_signals(frame, "FPT")
    assert list(signals.columns) == SIGNAL_COLUMNS
    if not signals.empty:
        assert (signals["symbol"] == "FPT").all()
        assert (signals["stop_loss"] < signals["target"]).all()


def test_generate_buy_signals_only_uses_data_up_to_each_bar():
    """Khong nhin truoc tuong lai: tin hieu tai phien i phai giong nhau du
    frame co bi cat ngan sau phien i bao nhieu di nua."""
    frame = _uptrend_frame(n=220)
    full_signals = generate_buy_signals(frame, "FPT")

    cutoff = 150
    truncated = frame.iloc[:cutoff].reset_index(drop=True)
    truncated_signals = generate_buy_signals(truncated, "FPT")

    early_full = full_signals[full_signals["time"] < frame["time"].iloc[cutoff]]
    pd.testing.assert_frame_equal(
        early_full.reset_index(drop=True), truncated_signals.reset_index(drop=True)
    )


def test_signals_feed_into_backtest_engine_and_produce_valid_report():
    frame = _uptrend_frame(n=260)
    signals = generate_buy_signals(frame, "FPT")
    if signals.empty:
        return  # du lieu ngau nhien co the khong sinh tin hieu nao, bo qua an toan

    result = run({"FPT": frame}, signals, initial_capital=100_000_000)
    stats = metrics.summarise(result.equity, result.trades)

    assert not result.equity.empty
    assert "CAGR" in stats
    assert "Sut giam toi da" in stats
