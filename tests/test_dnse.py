"""Kiem thu ngat mach DNSE: may chu khong ket noi duoc (vd Render o Singapore)
thi bao loi NGAY de router chuyen sang Vietcap, khong treo lenh nhieu phut."""
from __future__ import annotations

import json
import time
from datetime import date

import pytest
import urllib3

from bot_phan_tich.data import dnse
from bot_phan_tich.data.base import ProviderError
from bot_phan_tich.data.dnse import DnseProvider, DnseUnreachable


class FakeClient:
    def __init__(self, error: Exception | None = None, body: dict | None = None):
        self.error = error
        self.body = body or {"t": [1_700_000_000], "o": [1], "h": [1], "l": [1], "c": [1], "v": [1]}
        self.calls = 0

    def get_ohlc(self, _market_type, query=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return 200, json.dumps(self.body)


def _connect_timeout() -> urllib3.exceptions.MaxRetryError:
    reason = urllib3.exceptions.ConnectTimeoutError(None, "Connection to DNSE timed out")
    return urllib3.exceptions.MaxRetryError(None, "/price/ohlc", reason)


@pytest.fixture(autouse=True)
def reset_breaker(monkeypatch):
    monkeypatch.setattr(dnse, "_down_until", 0.0)


def _provider(client: FakeClient) -> DnseProvider:
    provider = DnseProvider()
    provider._client = client
    return provider


def test_connection_error_is_not_retried_and_opens_breaker():
    client = FakeClient(error=_connect_timeout())
    provider = _provider(client)

    with pytest.raises(DnseUnreachable):
        provider.ohlcv("FPT", date(2026, 1, 1), date(2026, 2, 1))
    assert client.calls == 1  # khong thu lai 5 lan

    started = time.monotonic()
    with pytest.raises(DnseUnreachable, match="tam bo qua"):
        provider.ohlcv("VNM", date(2026, 1, 1), date(2026, 2, 1))
    assert client.calls == 1  # dang ngat mach: khong goi mang
    assert time.monotonic() - started < 0.5


def test_unreachable_is_a_provider_error_for_router_fallback():
    assert issubclass(DnseUnreachable, ProviderError)


def test_breaker_closes_after_cooldown(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(dnse, "_down_until", time.monotonic() - 1)  # het han
    frame = _provider(client).ohlcv("FPT", date(2026, 1, 1), date(2026, 2, 1))
    assert client.calls == 1
    assert len(frame) == 1


def test_probe_reports_unreachable_quickly():
    status, bars, error = _provider(FakeClient(error=_connect_timeout())).probe_ohlc("FPT")
    assert status is None and bars == 0
    assert "không kết nối được" in error


def test_sdk_client_gets_short_connect_timeout(monkeypatch):
    pytest.importorskip("dnse")
    from bot_phan_tich.config import Secrets

    monkeypatch.setattr(
        dnse, "get_secrets", lambda: Secrets(dnse_api_key="k", dnse_api_secret="s")
    )
    client = DnseProvider().client
    timeout = client._http.connection_pool_kw["timeout"]
    assert timeout.connect_timeout == dnse._CONNECT_TIMEOUT
    assert client._http.connection_pool_kw["retries"].connect == 0
