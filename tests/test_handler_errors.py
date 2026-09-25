"""Thong bao loi cua /kn va /fin: nhanh va de hieu, khong lo chi tiet ky thuat."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from bot_phan_tich.bot.handlers import finreport, recommend
from bot_phan_tich.data.base import ProviderError


def test_unlisted_symbol_rejected_without_network(monkeypatch):
    monkeypatch.setattr(recommend.market_store, "load_symbols",
                        lambda: pd.DataFrame({"symbol": ["FPT", "HPG"], "exchange": "HOSE"}))

    class NoNetwork:
        def ohlcv(self, *_a, **_k):
            raise AssertionError("khong duoc goi mang cho ma khong niem yet")

    monkeypatch.setattr(recommend, "get_router", lambda: NoNetwork())
    started = time.monotonic()
    with pytest.raises(ValueError, match="không có trong danh sách niêm yết"):
        recommend._load_frame("ZZZ")
    assert time.monotonic() - started < 0.5


def test_provider_error_becomes_friendly_message(monkeypatch):
    monkeypatch.setattr(recommend.market_store, "load_symbols", lambda: pd.DataFrame())

    class Broken:
        def ohlcv(self, *_a, **_k):
            raise ProviderError('dnse: HTTP 400 {"status":400,"code":"BAD_REQUEST"}')

    monkeypatch.setattr(recommend, "get_router", lambda: Broken())
    with pytest.raises(ValueError) as info:
        recommend._load_frame("ABCD")
    assert "thử lại sau" in str(info.value)
    assert "BAD_REQUEST" not in str(info.value)


def test_fin_explains_empty_financials(monkeypatch):
    class Empty:
        def financials(self, *_a, **_k):
            return {k: pd.DataFrame() for k in ("income", "balance", "cashflow", "ratios")}

    monkeypatch.setattr(finreport, "get_router", lambda: Empty())
    text = finreport._build_commentary("HPG", None)
    assert "Chưa lấy được báo cáo tài chính" in text and "1 phút" in text
