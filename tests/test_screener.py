import numpy as np
import pandas as pd

from bot_phan_tich.analysis import screener as screener_mod
from bot_phan_tich.analysis.scoring import ACTION_ACCUMULATE


class FakeRouter:
    """Gia lap DataRouter cho screener - toan bo du lieu lay tu dict co san."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames

    def listing(self, exchanges=None):
        return pd.DataFrame(
            {"symbol": list(self.frames), "exchange": ["HOSE"] * len(self.frames)}
        )

    def industry_map(self):
        return pd.DataFrame(columns=["symbol", "industry"])

    def company_overview(self, symbol):
        return {}

    def ohlcv(self, symbol, start, end):
        return self.frames[symbol]

    def financials(self, symbol, period="quarter"):
        return {"ratios": pd.DataFrame()}


class FakeSettingsZeroTimeout:
    def get(self, key, default=None):
        if key == "screener.timeout_seconds":
            return 0.0
        return default


def _trend_frame(n=120, start=50.0, end=150.0) -> pd.DataFrame:
    close = np.linspace(start, end, n)
    return pd.DataFrame(
        {
            "time": pd.date_range("2023-01-01", periods=n, freq="B"),
            "open": close, "high": close, "low": close, "close": close,
            "volume": np.full(n, 100_000.0),
        }
    )


def test_presets_return_expected_criteria():
    assert screener_mod.preset_breakout().price_vs_kumo == "tren_may"
    assert screener_mod.preset_breakout().macd_cross == "golden"
    assert screener_mod.preset_accumulate().price_vs_kumo == "trong_may"
    assert screener_mod.preset_warning().alert_mode is True


def test_screen_filters_by_min_action(monkeypatch):
    frames = {
        "AAA": _trend_frame(start=50.0, end=150.0),   # xu huong tang manh
        "BBB": _trend_frame(start=150.0, end=50.0),   # xu huong giam manh
    }
    monkeypatch.setattr(screener_mod, "get_router", lambda: FakeRouter(frames))

    criteria = screener_mod.ScreenCriteria(symbols=list(frames), min_action=ACTION_ACCUMULATE)
    results = screener_mod.screen(criteria)
    found = {r.symbol for r in results}

    assert "AAA" in found
    assert "BBB" not in found


def test_screen_report_stops_on_timeout_and_sets_note(monkeypatch):
    frames = {f"S{i}": _trend_frame() for i in range(5)}
    monkeypatch.setattr(screener_mod, "get_router", lambda: FakeRouter(frames))
    monkeypatch.setattr(screener_mod, "get_settings", lambda: FakeSettingsZeroTimeout())

    report = screener_mod.screen_report(screener_mod.ScreenCriteria(symbols=list(frames)))

    assert report.timed_out is True
    assert report.note is not None
    assert report.scanned < report.total


def test_screen_results_are_sorted_by_score_descending():
    frames = {
        "AAA": _trend_frame(start=50.0, end=150.0),
        "BBB": _trend_frame(start=50.0, end=90.0),
    }

    class LocalRouter(FakeRouter):
        pass

    import bot_phan_tich.analysis.screener as mod

    original_get_router = mod.get_router
    mod.get_router = lambda: LocalRouter(frames)
    try:
        results = mod.screen(mod.ScreenCriteria(symbols=list(frames)))
    finally:
        mod.get_router = original_get_router

    scores = [r.total_score for r in results]
    assert scores == sorted(scores, reverse=True)
