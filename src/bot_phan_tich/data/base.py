"""Giao dien truu tuong cho moi nguon du lieu.

Muc dich: phan con lai cua he thong KHONG duoc biet du lieu den tu DNSE hay
Vietcap. Doi nguon chi can them mot lop con o day va sua config/settings.yaml.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

# Khung DataFrame chuan cho chuoi gia, moi module phia sau deu gia dinh dung cot nay.
OHLCV_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


class ProviderError(RuntimeError):
    """Nguon du lieu that bai. Router bat loi nay de chuyen sang nguon ke tiep."""


class PriceProvider(ABC):
    """Nguon cung cap du lieu gia."""

    name: str = "base"

    @abstractmethod
    def ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        resolution: str = "1D",
    ) -> pd.DataFrame:
        """Tra ve DataFrame co dung cac cot trong OHLCV_COLUMNS, sap xep tang dan theo time."""

    @abstractmethod
    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        """Danh sach ma niem yet. Cot toi thieu: symbol, exchange, organ_name."""

    def foreign_flow(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Giao dich khoi ngoai theo phien. Cot: time, foreign_buy_volume, foreign_sell_volume.

        Nguon nao khong ho tro thi tra DataFrame rong, tang L2 se bo qua tin hieu nay.
        """
        return pd.DataFrame(columns=["time", "foreign_buy_volume", "foreign_sell_volume"])


class FundamentalProvider(ABC):
    """Nguon cung cap bao cao tai chinh."""

    name: str = "base"

    @abstractmethod
    def income_statement(self, symbol: str, period: str = "quarter") -> pd.DataFrame: ...

    @abstractmethod
    def balance_sheet(self, symbol: str, period: str = "quarter") -> pd.DataFrame: ...

    @abstractmethod
    def cash_flow(self, symbol: str, period: str = "quarter") -> pd.DataFrame: ...

    @abstractmethod
    def ratios(self, symbol: str, period: str = "quarter") -> pd.DataFrame: ...

    def industry_map(self) -> pd.DataFrame:
        """Anh xa ma -> nganh. Cot: symbol, industry."""
        return pd.DataFrame(columns=["symbol", "industry"])

    def company_overview(self, symbol: str) -> dict:
        """Ho so doanh nghiep: ten day du, ngay niem yet, von dieu le, so
        luong CP luu hanh, mo ta hoat dong.

        TODO: chua co nguon xac nhan cung cap day du cac truong nay tai thoi
        diem viet (xem docs/lay-api.md). Nguon nao cai duoc thi tra dict voi
        cac khoa: full_name, listed_date, charter_capital, shares_outstanding,
        description - khoa nao khong co thi bo qua (dung .get() o phia goi).
        Mac dinh tra dict rong, KHONG bia du lieu.
        """
        return {}
