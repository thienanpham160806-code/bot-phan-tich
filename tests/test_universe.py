import pandas as pd
import pytest

from bot_phan_tich.config import Paths
from bot_phan_tich.data import market_store, universe


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(market_store, "get_paths", lambda: paths)
    market_store._cache.clear()
    return paths


def _daily_rows(symbol: str, n: int, price: float, volume: float) -> list[list]:
    dates = pd.bdate_range("2023-01-02", periods=n)
    return [
        [symbol, d.strftime("%Y-%m-%d"), price, price * 1.01, price * 0.99, price, volume]
        for d in dates
    ]


def test_liquid_universe_empty_store_returns_empty_list(isolated_store):
    assert universe.liquid_universe() == []


def test_liquid_universe_filters_by_price_volume_and_history(isolated_store):
    rows = []
    rows += _daily_rows("AAA", 260, price=20_000, volume=200_000)   # dat het dieu kien
    rows += _daily_rows("BBB", 260, price=1_000, volume=200_000)    # gia qua thap
    rows += _daily_rows("CCC", 260, price=20_000, volume=5_000)     # khoi luong qua thap
    rows += _daily_rows("DDD", 50, price=20_000, volume=200_000)    # chua du so phien
    frame = pd.DataFrame(rows, columns=market_store.OHLCV_COLUMNS)
    market_store.save_ohlcv(frame, merge=False)
    market_store.save_symbols(
        pd.DataFrame(
            {"symbol": ["AAA", "BBB", "CCC", "DDD"], "exchange": ["HOSE"] * 4}
        )
    )

    result = universe.liquid_universe()
    assert result == ["AAA"]


def test_liquid_universe_use_watchlist_bypasses_store(isolated_store, monkeypatch):
    monkeypatch.setattr(
        universe, "get_universe_config", lambda: {"watchlist": ["fpt", "vnm"]}
    )
    assert universe.liquid_universe(use_watchlist=True) == ["FPT", "VNM"]
