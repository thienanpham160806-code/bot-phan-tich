"""Nguon du lieu DNSE qua SDK chinh thuc (pip install openapi-sdk).

Tai lieu: https://developers.dnse.com.vn
Repo SDK: https://github.com/dnse-tech/openapi-sdk

LUU Y CHO NGUOI LAM TIEP:
Ten phuong thuc cua SDK co the doi giua cac phien ban. Truoc khi viet tiep,
chay thu de xem SDK dang co nhung ham gi:

    from dnse import DNSEClient
    client = DNSEClient(api_key=..., api_secret=...)
    print([m for m in dir(client) if not m.startswith("_")])

Sau do chinh lai cac loi goi trong _call_ohlc / _call_instruments cho khop.
Toan bo phan con lai cua he thong khong bi anh huong vi da di qua PriceProvider.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from ..config import get_secrets
from ..logging_conf import get_logger
from .base import OHLCV_COLUMNS, PriceProvider, ProviderError

log = get_logger(__name__)

# Anh xa do phan giai noi bo -> do phan giai cua DNSE.
RESOLUTION_MAP = {"1m": "1", "5m": "5", "15m": "15", "1H": "60", "1D": "1D"}


def _to_epoch(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())


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
                    "Chua cai SDK cua DNSE. Chay: pip install openapi-sdk"
                ) from exc

            self._client = DNSEClient(
                api_key=secrets.dnse_api_key,
                api_secret=secrets.dnse_api_secret,
                base_url=secrets.dnse_base_url,
                api_version=secrets.dnse_api_version,
            )
            log.info("Da khoi tao DNSE client (%s)", secrets.dnse_base_url)
        return self._client

    # ------------------------------------------------------------------- goi API
    @retry(
        retry=retry_if_exception_type(ProviderError),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=30),
        reraise=True,
    )
    def _call_ohlc(self, symbol: str, start: date, end: date, resolution: str) -> object:
        """Goi endpoint OHLC. Tach rieng de de sua khi SDK doi chu ky ham."""
        try:
            return self.client.get_ohlc(
                symbol=symbol,
                resolution=RESOLUTION_MAP.get(resolution, "1D"),
                from_=_to_epoch(start),
                to=_to_epoch(end),
            )
        except Exception as exc:  # SDK nem nhieu loai loi khac nhau
            raise ProviderError(f"DNSE get_ohlc that bai cho {symbol}: {exc}") from exc

    def _call_instruments(self) -> object:
        try:
            return self.client.get_instruments()
        except Exception as exc:
            raise ProviderError(f"DNSE get_instruments that bai: {exc}") from exc

    # --------------------------------------------------------------- PriceProvider
    def ohlcv(
        self, symbol: str, start: date, end: date, resolution: str = "1D"
    ) -> pd.DataFrame:
        raw = self._call_ohlc(symbol, start, end, resolution)
        frame = _normalise_ohlc(raw)
        if frame.empty:
            raise ProviderError(f"DNSE tra ve rong cho {symbol}")
        frame["symbol"] = symbol.upper()
        return frame

    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        raw = self._call_instruments()
        frame = pd.DataFrame(raw if isinstance(raw, list) else getattr(raw, "data", []) or [])
        if frame.empty:
            raise ProviderError("DNSE tra ve danh sach ma rong")

        rename = {"symbol": "symbol", "exchange": "exchange", "companyName": "organ_name"}
        frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
        if exchanges:
            wanted = {e.upper() for e in exchanges}
            frame = frame[frame["exchange"].str.upper().isin(wanted)]
        return frame.reset_index(drop=True)


def _normalise_ohlc(raw: object) -> pd.DataFrame:
    """Dua nhieu dang tra ve khac nhau ve cung mot khung DataFrame chuan.

    DNSE co the tra ve dict dang {t: [...], o: [...], ...} hoac danh sach ban ghi.
    Ham nay chiu trach nhiem lam phang su khac biet do.
    """
    payload = raw
    if isinstance(raw, tuple) and len(raw) == 2:  # SDK tra (status, body)
        payload = raw[1]
    if hasattr(payload, "data"):
        payload = payload.data

    if isinstance(payload, dict) and "t" in payload:
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
    elif isinstance(payload, list):
        frame = pd.DataFrame(payload)
        alias = {
            "t": "time", "tradingDate": "time", "date": "time",
            "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
        }
        frame = frame.rename(columns={k: v for k, v in alias.items() if k in frame.columns})
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=False)
    else:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    for col in OHLCV_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[OHLCV_COLUMNS].dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
