from datetime import datetime, timedelta

import pandas as pd
import pytest

from bot_phan_tich.config import Paths
from bot_phan_tich.data import fundamentals_store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(fundamentals_store, "get_paths", lambda: paths)
    fundamentals_store._cache.clear()
    return paths


def _frame():
    return pd.DataFrame(
        {
            "symbol": ["fpt", "vnm"],
            "pe": [18.5, 12.0],
            "pb": [3.2, 1.8],
            "roe": [25.0, 15.0],
            "updated_at": [pd.Timestamp.now(), pd.Timestamp.now()],
        }
    )


def test_load_fundamentals_empty_when_no_store(isolated_store):
    frame = fundamentals_store.load_fundamentals()
    assert frame.empty
    assert fundamentals_store.fundamentals_last_updated() is None


def test_save_and_load_roundtrip_uppercases_symbols(isolated_store):
    total = fundamentals_store.save_fundamentals(_frame())
    assert total == 2

    loaded = fundamentals_store.load_fundamentals()
    assert set(loaded["symbol"]) == {"FPT", "VNM"}
    assert loaded.loc[loaded["symbol"] == "FPT", "pe"].iloc[0] == 18.5


def test_is_stale_true_when_no_store(isolated_store):
    assert fundamentals_store.is_stale() is True


def test_is_stale_false_when_within_cache_window(isolated_store):
    fundamentals_store.save_fundamentals(_frame())
    assert fundamentals_store.is_stale(max_age_days=7) is False


def test_is_stale_true_when_older_than_cache_window(isolated_store, monkeypatch):
    fundamentals_store.save_fundamentals(_frame())
    future = datetime.now() + timedelta(days=8)
    assert fundamentals_store.is_stale(max_age_days=7, now=future) is True


def test_cache_invalidates_when_file_changes(isolated_store):
    fundamentals_store.save_fundamentals(_frame())
    first = fundamentals_store.load_fundamentals()
    assert len(first) == 2

    smaller = pd.DataFrame(
        {
            "symbol": ["fpt"], "pe": [18.5], "pb": [3.2], "roe": [25.0],
            "updated_at": [pd.Timestamp.now()],
        }
    )
    fundamentals_store.save_fundamentals(smaller)
    second = fundamentals_store.load_fundamentals()
    assert len(second) == 1  # khong bi "dinh" du lieu cu tu lan doc truoc
