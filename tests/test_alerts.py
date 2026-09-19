import numpy as np
import pandas as pd
import pytest

from bot_phan_tich.alerts import eod as eod_mod
from bot_phan_tich.alerts import watchlist
from bot_phan_tich.config import Paths
from bot_phan_tich.data import cache as cache_mod


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Moi test dung mot file SQLite rieng, khong dung chung ./data/cache.sqlite3."""
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(cache_mod, "get_paths", lambda: paths)
    cache_mod.init_db()
    return paths


class FakeRouter:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def ohlcv(self, symbol, start, end):
        return self.frame


def _flat_frame(n: int = 100, price: float = 100.0) -> pd.DataFrame:
    close = np.full(n, price)
    return pd.DataFrame(
        {
            "time": pd.date_range("2023-01-01", periods=n, freq="B"),
            "open": close, "high": close, "low": close, "close": close,
            "volume": np.full(n, 100_000.0),
        }
    )


def _bullish_frame(n: int = 100) -> pd.DataFrame:
    close = np.linspace(80.0, 200.0, n)
    return pd.DataFrame(
        {
            "time": pd.date_range("2023-01-01", periods=n, freq="B"),
            "open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
            "volume": np.full(n, 100_000.0),
        }
    )


# --------------------------------------------------------------- watchlist.py
def test_watchlist_add_remove_and_list(isolated_db):
    watchlist.add(111, "fpt")
    watchlist.add(111, "hpg")
    watchlist.add(222, "fpt")

    assert watchlist.list_symbols(111) == ["FPT", "HPG"]
    assert set(watchlist.subscribers_of("FPT")) == {111, 222}

    watchlist.remove(111, "hpg")
    assert watchlist.list_symbols(111) == ["FPT"]


def test_alerts_toggle_defaults_to_enabled(isolated_db):
    assert watchlist.is_alerts_enabled(999) is True
    watchlist.set_alerts_enabled(999, False)
    assert watchlist.is_alerts_enabled(999) is False
    assert watchlist.toggle_alerts(999) is True


# ----------------------------------------------------------- phat hien thay doi
_BASE_STATE = {
    "action": "THEO DÕI", "macd_cross": None,
    "price_vs_kumo": "trong_may", "rsi_zone": "trung_tinh",
}


def test_detect_significant_change_none_when_first_seen():
    today = {**_BASE_STATE, "action": "MUA", "price_vs_kumo": "tren_may"}
    assert eod_mod._detect_significant_change(None, today, vol_ratio=1.0, day_change_pct=0.01) == []


def test_detect_significant_change_flags_action_change():
    prev = dict(_BASE_STATE)
    today = {**_BASE_STATE, "action": "MUA"}
    reasons = eod_mod._detect_significant_change(prev, today, vol_ratio=1.0, day_change_pct=0.0)
    assert any("Khuyến nghị đổi" in r for r in reasons)


def test_detect_significant_change_flags_volume_spike():
    reasons = eod_mod._detect_significant_change(
        dict(_BASE_STATE), dict(_BASE_STATE), vol_ratio=2.5, day_change_pct=0.0
    )
    assert any("Khối lượng đột biến" in r for r in reasons)


def test_detect_significant_change_flags_big_price_move():
    reasons = eod_mod._detect_significant_change(
        dict(_BASE_STATE), dict(_BASE_STATE), vol_ratio=1.0, day_change_pct=0.05
    )
    assert any("biến động" in r for r in reasons)


def test_detect_significant_change_empty_when_nothing_changed():
    reasons = eod_mod._detect_significant_change(
        dict(_BASE_STATE), dict(_BASE_STATE), vol_ratio=1.0, day_change_pct=0.0
    )
    assert reasons == []


# ------------------------------------------------------------------- run_eod_scan
def test_scan_one_symbol_caps_alerts_per_day(isolated_db):
    router = FakeRouter(_flat_frame())
    eod_mod._scan_one_symbol("AAA", router)  # lan dau: luu trang thai, khong canh bao

    alert_count = 0
    for i in range(6):
        router.frame = _bullish_frame() if i % 2 == 0 else _flat_frame()
        if eod_mod._scan_one_symbol("AAA", router):
            alert_count += 1

    assert alert_count == eod_mod._MAX_ALERTS_PER_SYMBOL_PER_DAY


def test_run_eod_scan_alerts_on_change_and_merges_per_chat(isolated_db, monkeypatch):
    watchlist.add(111, "AAA")
    watchlist.add(111, "BBB")

    router1 = FakeRouter(_flat_frame())
    monkeypatch.setattr(eod_mod, "get_router", lambda: router1)
    assert eod_mod.run_eod_scan() == []  # lan dau chua co gi de so sanh

    router2 = FakeRouter(_bullish_frame())
    monkeypatch.setattr(eod_mod, "get_router", lambda: router2)
    alerts = eod_mod.run_eod_scan()

    assert len(alerts) == 1
    assert alerts[0].chat_id == 111
    joined = "\n".join(alerts[0].lines)
    assert "AAA" in joined and "BBB" in joined


def test_run_eod_scan_skips_chats_with_alerts_disabled(isolated_db, monkeypatch):
    watchlist.add(111, "AAA")
    watchlist.set_alerts_enabled(111, False)

    router1 = FakeRouter(_flat_frame())
    monkeypatch.setattr(eod_mod, "get_router", lambda: router1)
    eod_mod.run_eod_scan()

    router2 = FakeRouter(_bullish_frame())
    monkeypatch.setattr(eod_mod, "get_router", lambda: router2)
    alerts = eod_mod.run_eod_scan()

    assert alerts == []
