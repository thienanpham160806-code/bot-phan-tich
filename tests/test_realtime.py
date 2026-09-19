import pytest

from bot_phan_tich.data.realtime import (
    DnseRealtimeProvider,
    NullRealtimeProvider,
    VietcapRealtimeProvider,
    get_realtime_provider,
)


def test_get_realtime_provider_defaults_to_null_when_disabled():
    # config/settings.yaml mac dinh realtime.enabled: false
    provider = get_realtime_provider()
    assert isinstance(provider, NullRealtimeProvider)


def test_null_provider_never_raises():
    provider = NullRealtimeProvider()
    provider.subscribe(["FPT"])
    provider.unsubscribe(["FPT"])
    assert provider.latest("FPT") is None
    provider.close()


def test_dnse_stub_raises_not_implemented():
    provider = DnseRealtimeProvider()
    with pytest.raises(NotImplementedError):
        provider.subscribe(["FPT"])
    with pytest.raises(NotImplementedError):
        provider.latest("FPT")


def test_vietcap_stub_raises_not_implemented():
    provider = VietcapRealtimeProvider()
    with pytest.raises(NotImplementedError):
        provider.subscribe(["FPT"])
