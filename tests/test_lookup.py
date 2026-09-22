import pandas as pd

from bot_phan_tich.analysis import lookup as lookup_mod


class FakeRouter:
    """Gia lap DataRouter, khong goi mang - dung de kiem tra lookup() rieng biet."""

    def __init__(self):
        self.listing_df = pd.DataFrame(
            {"symbol": ["FPT"], "exchange": ["HOSE"], "organ_name": ["CTCP FPT"]}
        )
        self.industry_df = pd.DataFrame(
            {"symbol": ["FPT", "CMG"], "industry": ["Cong nghe", "Cong nghe"]}
        )
        close = list(range(100, 110))
        self.price_frame = pd.DataFrame(
            {
                "time": pd.date_range("2024-01-01", periods=10),
                "open": close, "high": close, "low": close, "close": close,
                "volume": [1_000] * 10,
            }
        )
        self.ratios = pd.DataFrame({"pe": [15.0], "pb": [2.0], "roe": [0.2]})
        self.income = pd.DataFrame({"year": [2023]})

    def listing(self, exchanges=None):
        return self.listing_df

    def industry_map(self):
        return self.industry_df

    def company_overview(self, symbol):
        return {}

    def company_news(self, symbol, days=180):
        return []

    def ohlcv(self, symbol, start, end):
        return self.price_frame

    def financials(self, symbol, period="quarter"):
        return {
            "income": self.income, "balance": pd.DataFrame(),
            "cashflow": pd.DataFrame(), "ratios": self.ratios,
        }


def test_lookup_fills_available_fields_and_notes_missing_ones(monkeypatch):
    fake = FakeRouter()
    monkeypatch.setattr(lookup_mod, "get_router", lambda: fake)

    profile = lookup_mod.lookup("fpt")

    assert profile.symbol == "FPT"
    assert profile.exchange == "HOSE"
    assert profile.full_name == "CTCP FPT"
    assert profile.industry == "Cong nghe"
    assert profile.price == 109.0
    assert profile.pe.value == 15.0
    assert profile.roe.value == 0.2
    assert profile.latest_report_period == "2023"

    # Khong co nguon xac nhan cho cac truong nay -> phai la None, khong bia so.
    assert profile.listed_date is None
    assert profile.charter_capital is None
    has_news_note = any(
        "công bố" in note.lower() or "tin tức" in note.lower() for note in profile.data_notes
    )
    assert has_news_note


def test_lookup_handles_provider_errors_without_raising(monkeypatch):
    class BrokenRouter(FakeRouter):
        def listing(self, exchanges=None):
            raise RuntimeError("nguon loi")

        def ohlcv(self, symbol, start, end):
            raise RuntimeError("nguon loi")

    monkeypatch.setattr(lookup_mod, "get_router", lambda: BrokenRouter())

    profile = lookup_mod.lookup("FPT")
    assert profile.symbol == "FPT"
    assert profile.price is None
    assert len(profile.data_notes) > 0
