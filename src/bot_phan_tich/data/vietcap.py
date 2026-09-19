"""Nguon du lieu Vietcap (VCI), truy cap qua thu vien vnstock.

Ly do di qua vnstock thay vi goi thang endpoint cua Vietcap:
  1. Vietcap khong cong bo tai lieu API chinh thuc cho nha dau tu ca nhan,
     endpoint noi bo co the doi bat ky luc nao.
  2. vnstock da chuan hoa ten cot bao cao tai chinh giua cac nguon, do chinh la
     phan ton cong nhat neu tu lam.

Doi lai, vnstock co gioi han tan suat goi. Vi vay moi ket qua deu di qua cache.

LUU Y: lan dau dung phai chay register_user() cua vnstock mot lan, sau do dat
VNSTOCK_ACCEPT_TOS=1 trong .env.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..logging_conf import get_logger
from .base import OHLCV_COLUMNS, FundamentalProvider, PriceProvider, ProviderError

log = get_logger(__name__)


class VietcapProvider(PriceProvider, FundamentalProvider):
    """Bao cao tai chinh, danh sach ma, nganh va gia du phong tu Vietcap/VCI."""

    name = "vietcap"

    def __init__(self) -> None:
        self._market = None
        self._reference = None
        self._fundamental = None

    # ------------------------------------------------------------------ lazy init
    def _modules(self):
        if self._market is None:
            try:
                from vnstock import Fundamental, Market, Reference  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise ProviderError("Chua cai vnstock. Chay: pip install -U vnstock") from exc
            self._market = Market()
            self._reference = Reference()
            self._fundamental = Fundamental()
            log.info("Da khoi tao vnstock (nguon Vietcap/VCI)")
        return self._market, self._reference, self._fundamental

    @staticmethod
    def _guard(fn, what: str):
        try:
            return fn()
        except Exception as exc:
            raise ProviderError(f"Vietcap/{what} that bai: {exc}") from exc

    # --------------------------------------------------------------- PriceProvider
    def ohlcv(
        self, symbol: str, start: date, end: date, resolution: str = "1D"
    ) -> pd.DataFrame:
        market, _, _ = self._modules()
        raw = self._guard(
            lambda: market.equity.ohlcv(
                symbol=symbol.upper(), start=start.isoformat(), end=end.isoformat()
            ),
            f"ohlcv({symbol})",
        )
        frame = pd.DataFrame(raw)
        alias = {"time": "time", "date": "time", "tradingDate": "time"}
        frame = frame.rename(columns={k: v for k, v in alias.items() if k in frame.columns})
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
        for col in OHLCV_COLUMNS:
            if col not in frame.columns:
                frame[col] = pd.NA
        frame = frame[OHLCV_COLUMNS].dropna(subset=["time"]).sort_values("time")
        frame["symbol"] = symbol.upper()
        return frame.reset_index(drop=True)

    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        _, reference, _ = self._modules()
        frame = pd.DataFrame(self._guard(lambda: reference.equity.list(), "listing"))
        if frame.empty:
            raise ProviderError("Vietcap tra ve danh sach ma rong")
        if exchanges and "exchange" in frame.columns:
            wanted = {e.upper() for e in exchanges}
            frame = frame[frame["exchange"].astype(str).str.upper().isin(wanted)]
        return frame.reset_index(drop=True)

    # ----------------------------------------------------------- FundamentalProvider
    def income_statement(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        return pd.DataFrame(
            self._guard(
                lambda: fa.equity.income_statement(symbol=symbol.upper(), period=period),
                f"income_statement({symbol})",
            )
        )

    def balance_sheet(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        return pd.DataFrame(
            self._guard(
                lambda: fa.equity.balance_sheet(symbol=symbol.upper(), period=period),
                f"balance_sheet({symbol})",
            )
        )

    def cash_flow(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        return pd.DataFrame(
            self._guard(
                lambda: fa.equity.cash_flow(symbol=symbol.upper(), period=period),
                f"cash_flow({symbol})",
            )
        )

    def ratios(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        return pd.DataFrame(
            self._guard(
                lambda: fa.equity.ratios(symbol=symbol.upper(), period=period),
                f"ratios({symbol})",
            )
        )

    def industry_map(self) -> pd.DataFrame:
        _, reference, _ = self._modules()
        frame = pd.DataFrame(
            self._guard(lambda: reference.equity.list_by_industry(), "industry_map")
        )
        keep = [c for c in ("symbol", "industry", "icb_name3", "icb_name2") if c in frame.columns]
        return frame[keep] if keep else frame
