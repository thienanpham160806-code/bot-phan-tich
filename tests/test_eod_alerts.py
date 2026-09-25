"""Kiem thu canh bao cuoi phien: gioi han so canh bao tinh theo NGAY."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from bot_phan_tich.alerts import eod
from bot_phan_tich.config import Paths
from bot_phan_tich.data import cache


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(cache, "get_paths", lambda: paths)
    cache.init_db()
    return paths


class FakeRouter:
    def __init__(self):
        n = 120
        close = 20 + np.cumsum(np.random.default_rng(0).normal(0, 0.3, n))
        self.frame = pd.DataFrame({
            "time": pd.bdate_range(end="2026-09-24", periods=n), "open": close,
            "high": close + 0.3, "low": close - 0.3, "close": close, "volume": 1e6,
        })

    def ohlcv(self, *_a, **_k):
        return self.frame


def _run_day(monkeypatch, day: date, router: FakeRouter) -> bool:
    class FixedDate(date):
        @classmethod
        def today(cls):
            return day

    monkeypatch.setattr(eod, "date", FixedDate)
    # Lan quet nao cung co ly do canh bao (gia bien dong manh).
    monkeypatch.setattr(eod, "_detect_significant_change", lambda *a, **k: ["Giá biến động"])
    return eod._scan_one_symbol("AAA", router) is not None


def test_alert_limit_resets_every_day(isolated_db, monkeypatch):
    router = FakeRouter()
    # 3 lan trong cung mot ngay: du han muc, lan thu 4 bi chan.
    same_day = [_run_day(monkeypatch, date(2026, 9, 21), router) for _ in range(4)]
    assert same_day == [True, True, True, False]
    # Sang ngay moi: phai canh bao lai duoc (ban cu cong don -> im lang mai).
    assert _run_day(monkeypatch, date(2026, 9, 22), router) is True
