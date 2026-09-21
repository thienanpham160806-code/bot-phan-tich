"""Nguon du lieu Vietcap (VCI), truy cap qua thu vien vnstock.

Ly do di qua vnstock thay vi goi thang endpoint cua Vietcap:
  1. Vietcap khong cong bo tai lieu API chinh thuc cho nha dau tu ca nhan,
     endpoint noi bo co the doi bat ky luc nao.
  2. vnstock da chuan hoa ten cot bao cao tai chinh giua cac nguon, do chinh la
     phan ton cong nhat neu tu lam.

Doi lai, vnstock co gioi han tan suat goi. Vi vay moi ket qua deu di qua cache.

LUU Y: lan dau dung phai chay register_user() cua vnstock mot lan, sau do
dat VNSTOCK_ACCEPT_TOS=1 trong .env.

DA XAC NHAN (kiem tra truc tiep tren vnstock 4.0.8, khong con la gia dinh):
  - `Market().equity` va `Fundamental().equity` la HAM, phai GOI voi symbol
    truoc (vd `market.equity(symbol="FPT")`) de lay ve doi tuong co cac
    phuong thuc thuc su (ohlcv/income_statement/...) - KHONG PHAI thuoc tinh
    long nhau nhu `market.equity.ohlcv(...)`.
  - `Reference().equity` la DOI TUONG (khong phai ham) - `list()`/
    `list_by_industry()` goi truc tiep duoc.
  - `income_statement`/`balance_sheet`/`cash_flow`/`ratios` tra ve dang
    "moi CHI TIEU la mot hang, moi KY la mot cot" (cot `item`, `item_id`,
    roi cac cot nam/quy). Phai xoay lai (_reshape_periods) thanh "moi KY la
    mot hang" de khop voi cach analysis/fintext.py va analysis/lookup.py
    doc du lieu (mot dong cho moi nam, tra cuu theo ten cot = item_id).
  - `ref.equity.list()` CHI co 2 cot (symbol, organ_name) - Vietcap khong
    tra ve san niem yet qua duong nay. `list_by_industry()` co `icb_name`
    voi 4 muc do chi tiet (icb_level 1-4); chon muc 4 (chi tiet nhat, vd
    "Moi gioi chung khoan" thay vi "Tai chinh") va doi ten cot thanh
    "industry" cho khop quy uoc chung cua he thong.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..logging_conf import get_logger
from .base import OHLCV_COLUMNS, FundamentalProvider, PriceProvider, ProviderError

log = get_logger(__name__)

_INDUSTRY_LEVEL = 4  # 1=rong nhat (vd "Tai chinh") .. 4=chi tiet nhat


def _reshape_periods(frame: pd.DataFrame) -> pd.DataFrame:
    """Xoay bao cao tai chinh cua vnstock (chi tieu=hang, ky=cot) thanh
    (ky=hang, item_id=cot) - dang ma analysis/fintext.py va analysis/lookup.py
    gia dinh (mot dong moi nam, tra cuu chi so theo ten cot).
    """
    if frame is None or frame.empty or "item_id" not in frame.columns:
        return pd.DataFrame()

    period_cols = [c for c in frame.columns if c not in ("item", "item_id")]
    # Bo hang toan NaN (thuong la dong tieu de/section header khong co so
    # lieu, vd "TAI SAN"), roi giu 1 dong cho moi item_id neu bi trung
    # (uu tien dong xuat hien SAU - thuong la dong tong hop co gia tri that).
    body = frame.dropna(subset=period_cols, how="all")
    body = body.drop_duplicates(subset="item_id", keep="last")

    reshaped = body.set_index("item_id")[period_cols].T
    reshaped.index.name = "period"
    return reshaped.sort_index().reset_index()


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
            lambda: market.equity(symbol=symbol.upper()).ohlcv(
                start=start.isoformat(), end=end.isoformat(), interval=resolution
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
        # LUU Y: nguon nay KHONG co cot san niem yet (chi symbol, organ_name).
        # Loc theo `exchanges` chi co tac dung khi nguon khac (DNSE) da dien
        # duoc cot "exchange" truoc do trong cung mot lan goi router.
        if exchanges and "exchange" in frame.columns:
            wanted = {e.upper() for e in exchanges}
            frame = frame[frame["exchange"].astype(str).str.upper().isin(wanted)]
        return frame.reset_index(drop=True)

    # ----------------------------------------------------------- FundamentalProvider
    def income_statement(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).income_statement(period=period),
            f"income_statement({symbol})",
        )
        return _reshape_periods(frame)

    def balance_sheet(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).balance_sheet(period=period),
            f"balance_sheet({symbol})",
        )
        return _reshape_periods(frame)

    def cash_flow(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).cash_flow(period=period),
            f"cash_flow({symbol})",
        )
        return _reshape_periods(frame)

    def ratios(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).ratios(period=period),
            f"ratios({symbol})",
        )
        return _reshape_periods(frame)

    def industry_map(self) -> pd.DataFrame:
        _, reference, _ = self._modules()
        frame = pd.DataFrame(
            self._guard(lambda: reference.equity.list_by_industry(), "industry_map")
        )
        if frame.empty or "icb_name" not in frame.columns:
            return frame
        frame = frame[frame.get("icb_level") == _INDUSTRY_LEVEL]
        frame = frame.rename(columns={"icb_name": "industry"})
        return frame[["symbol", "industry"]].reset_index(drop=True)
