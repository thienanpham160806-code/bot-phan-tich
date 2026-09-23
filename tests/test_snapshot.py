import numpy as np
import pandas as pd
import pytest

from bot_phan_tich.analysis import snapshot as snapshot_mod
from bot_phan_tich.config import Paths
from bot_phan_tich.data import fundamentals_store, market_store


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    for mod in (market_store, snapshot_mod, fundamentals_store):
        monkeypatch.setattr(mod, "get_paths", lambda: paths)
    market_store._cache.clear()
    fundamentals_store._cache.clear()
    return paths


def _random_walk(symbol: str, bars: int = 150, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 20_000 + np.cumsum(rng.normal(0, 200, bars))
    return pd.DataFrame(
        {
            "symbol": symbol,
            "time": pd.bdate_range("2024-01-01", periods=bars),
            "open": close, "high": close + 150, "low": close - 150, "close": close,
            "volume": rng.integers(200_000, 900_000, bars).astype(float),
        }
    )


def _seed_store(symbols: dict[str, int]) -> None:
    frames = [_random_walk(s, bars, seed=i) for i, (s, bars) in enumerate(symbols.items())]
    market_store.save_ohlcv(pd.concat(frames, ignore_index=True), merge=False)


def test_build_snapshot_reads_store_once_and_skips_short_history(isolated_paths, monkeypatch):
    _seed_store({"AAA": 150, "BBB": 150, "SHORT": 30})

    calls = []
    real_load = market_store.load_ohlcv

    def spy_load(*args, **kwargs):
        calls.append((args, kwargs))
        return real_load(*args, **kwargs)

    monkeypatch.setattr(market_store, "load_ohlcv", spy_load)

    frame = snapshot_mod.build_snapshot(["AAA", "BBB", "SHORT"])

    assert len(calls) == 1  # doc kho DUNG MOT LAN, khong doc lai cho tung ma
    assert set(frame["symbol"]) == {"AAA", "BBB"}  # SHORT < 60 phien -> bo qua
    assert snapshot_mod.snapshot_path().exists()


def test_build_snapshot_thread_pool_gives_same_rows(isolated_paths):
    _seed_store({"AAA": 150, "BBB": 150, "CCC": 150})

    sequential = snapshot_mod.build_snapshot(["AAA", "BBB", "CCC"], max_workers=1)
    threaded = snapshot_mod.build_snapshot(["AAA", "BBB", "CCC"], max_workers=3)

    cols = ["symbol", "action", "total_score"]
    pd.testing.assert_frame_equal(
        sequential[cols].sort_values("symbol").reset_index(drop=True),
        threaded[cols].sort_values("symbol").reset_index(drop=True),
    )


def test_build_snapshot_missing_symbol_is_skipped_not_crash(isolated_paths):
    _seed_store({"AAA": 150})
    frame = snapshot_mod.build_snapshot(["AAA", "NOT_IN_STORE"])
    assert list(frame["symbol"]) == ["AAA"]
