"""Nguon du lieu DNSE qua SDK chinh thuc.

`pip install openapi-sdk` (theo README cua DNSE) KHONG cai duoc - ten goi do
chi la vi du trong docs, KHONG phai ten that tren PyPI. Ten goi PyPI THAT su
la `dnse-sdk-openapi` (da xac nhan tren PyPI 22/09/2026 - xem requirements.txt),
cai binh thuong bang `pip install -r requirements.txt`, khong can vendor nua.
Import trong code van la `from dnse import DNSEClient` (khong doi ten module).

Cac chi tiet duoi day DA XAC NHAN truc tiep tu tai lieu API chinh thuc cua DNSE
(https://developers.dnse.com.vn) va tu doc source cua SDK (dnse/api/client.py):

  - Moi phuong thuc cua DNSEClient tra ve tuple (status_code, body_text),
    body_text la CHUOI JSON THO - phai tu json.loads(), SDK khong tu parse.
  - GET /price/ohlc: bat buoc symbol, resolution (1,3,5,15,30,1h,1D,1W), from,
    to (epoch giay). SDK: client.get_ohlc(bar_type, query={...}) - bar_type
    la LOAI THI TRUONG (STOCK/DERIVATIVE/INDEX), KHONG PHAI khung thoi gian;
    symbol/resolution/from/to nam trong `query`. Tra ve {t,o,h,l,c,v,nextTime}.
  - GET /market/instruments: tra ve {data: [...], total, page, pageSize}.
    Moi ban ghi co symbol, marketId (STO=HOSE, STX=HNX, UPX=UPCOM), name
    (ten day du), shortName, listedDate. KHONG co von dieu le / so CP luu
    hanh / mo ta hoat dong - de None, khong bia (xem company_overview()).

Repo con lai: https://github.com/dnse-tech/openapi-sdk . Tai lieu API:
https://developers.dnse.com.vn
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from ..config import get_secrets
from ..logging_conf import get_logger
from .base import OHLCV_COLUMNS, PriceProvider, ProviderError

log = get_logger(__name__)

# Anh xa do phan giai noi bo -> gia tri `resolution` DNSE chap nhan (xem
# spec /price/ohlc: "1,3,5,15,30,1h,1D,1W").
RESOLUTION_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1H": "1h", "1D": "1D", "1W": "1W",
}
# marketId (endpoint /market/instruments) -> ten san dung trong he thong.
MARKET_ID_TO_EXCHANGE = {"STO": "HOSE", "STX": "HNX", "UPX": "UPCOM"}
EXCHANGE_TO_MARKET_ID = {v: k for k, v in MARKET_ID_TO_EXCHANGE.items()}
_INDEX_SYMBOLS = {"VNINDEX", "HNXINDEX", "UPCOMINDEX", "VN30"}
_INSTRUMENTS_PAGE_SIZE = 100


def _to_epoch(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())


def _market_type_of(symbol: str) -> str:
    """"STOCK" cho ma co phieu thuong, "INDEX" cho VNINDEX/VN30... (best-effort)."""
    return "INDEX" if symbol.upper() in _INDEX_SYMBOLS else "STOCK"


class DnseProvider(PriceProvider):
    """Gia, khop lenh va danh sach ma tu DNSE OpenAPI."""

    name = "dnse"

    def __init__(self) -> None:
        self._client = None  # khoi tao tre: chi tao khi that su goi mang

    # ------------------------------------------------------------------ client
    @property
    def client(self):
        if self._client is None:
            secrets = get_secrets()
            if not secrets.dnse_api_key or not secrets.dnse_api_secret:
                raise ProviderError(
                    "Thieu DNSE_API_KEY / DNSE_API_SECRET trong .env. "
                    "Dang ky ung dung tai https://developers.dnse.com.vn"
                )
            try:
                from dnse import DNSEClient  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise ProviderError(
                    "Chua cai SDK cua DNSE. Chay: pip install -r requirements.txt "
                    "(goi PyPI: dnse-sdk-openapi)"
                ) from exc

            self._client = DNSEClient(
                api_key=secrets.dnse_api_key,
                api_secret=secrets.dnse_api_secret,
                base_url=secrets.dnse_base_url,
                api_version=secrets.dnse_api_version,
            )
            log.info("Da khoi tao DNSE client (%s)", secrets.dnse_base_url)
        return self._client

    @staticmethod
    def _parse_response(status: int | None, body: str | None, what: str) -> dict:
        """Kiem tra status va json.loads() body_text - DNSEClient khong tu parse."""
        if status is None or status >= 300:
            raise ProviderError(f"DNSE {what} tra ve HTTP {status}: {body}")
        try:
            return json.loads(body) if body else {}
        except (TypeError, ValueError) as exc:
            raise ProviderError(f"DNSE {what} tra ve JSON khong hop le: {exc}") from exc

    # ------------------------------------------------------------------- goi API
    @retry(
        retry=retry_if_exception_type(ProviderError),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=30),
        reraise=True,
    )
    def _call_ohlc(self, symbol: str, start: date, end: date, resolution: str) -> dict:
        try:
            status, body = self.client.get_ohlc(
                _market_type_of(symbol),
                query={
                    "symbol": symbol.upper(),
                    "resolution": RESOLUTION_MAP.get(resolution, "1D"),
                    "from": _to_epoch(start),
                    "to": _to_epoch(end),
                },
            )
        except Exception as exc:  # SDK nem nhieu loai loi khac nhau
            raise ProviderError(f"DNSE get_ohlc that bai cho {symbol}: {exc}") from exc
        return self._parse_response(status, body, f"get_ohlc({symbol})")

    def _call_instruments_page(self, market_id: str, page: int) -> dict:
        try:
            status, body = self.client.get_instruments(
                market_id=market_id, limit=_INSTRUMENTS_PAGE_SIZE, page=page
            )
        except Exception as exc:
            raise ProviderError(f"DNSE get_instruments that bai: {exc}") from exc
        return self._parse_response(status, body, "get_instruments")

    # --------------------------------------------------------------- PriceProvider
    def ohlcv(
        self, symbol: str, start: date, end: date, resolution: str = "1D"
    ) -> pd.DataFrame:
        payload = self._call_ohlc(symbol, start, end, resolution)
        frame = _normalise_ohlc(payload)
        if frame.empty:
            raise ProviderError(f"DNSE tra ve rong cho {symbol}")
        frame["symbol"] = symbol.upper()
        return frame

    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        if exchanges:
            wanted = [e.upper() for e in exchanges]
            market_ids = [EXCHANGE_TO_MARKET_ID[e] for e in wanted if e in EXCHANGE_TO_MARKET_ID]
        else:
            market_ids = list(MARKET_ID_TO_EXCHANGE)

        rows: list[dict] = []
        for market_id in market_ids:
            page = 1
            while True:
                payload = self._call_instruments_page(market_id, page)
                data = payload.get("data") or []
                rows.extend(data)
                total = payload.get("total", len(rows))
                if not data or page * _INSTRUMENTS_PAGE_SIZE >= total:
                    break
                page += 1

        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ProviderError("DNSE tra ve danh sach ma rong")

        frame["exchange"] = frame["marketId"].map(MARKET_ID_TO_EXCHANGE)
        frame["organ_name"] = frame.get("name", frame.get("shortName"))
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
        return frame[["symbol", "exchange", "organ_name"]].reset_index(drop=True)

    def company_overview(self, symbol: str) -> dict:
        """Ho so tu /market/instruments: chi co full_name + listed_date thuc
        su co du lieu. Von dieu le/so CP luu hanh/mo ta KHONG co trong
        endpoint nay - khong bia, de trong."""
        try:
            status, body = self.client.get_instruments(symbol=symbol.upper())
            payload = self._parse_response(status, body, f"get_instruments({symbol})")
        except ProviderError as exc:
            log.warning("company_overview(%s) that bai: %s", symbol, exc)
            return {}
        rows = payload.get("data") or []
        if not rows:
            return {}
        row = rows[0]
        return {
            "full_name": row.get("name") or row.get("shortName"),
            "listed_date": row.get("listedDate"),
        }


def _normalise_ohlc(payload: dict) -> pd.DataFrame:
    """DNSE tra ve {t,o,h,l,c,v,nextTime} (mang song song) cho GET /price/ohlc."""
    if not isinstance(payload, dict) or "t" not in payload:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(payload["t"], unit="s"),
            "open": payload.get("o"),
            "high": payload.get("h"),
            "low": payload.get("l"),
            "close": payload.get("c"),
            "volume": payload.get("v"),
        }
    )
    for col in OHLCV_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[OHLCV_COLUMNS].dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
