"""Kho du lieu gia TOAN SAN: mot file parquet duy nhat tren dia, doc mot lan.

Giai quyet van de: truoc day moi lan /loc hay /tinhieu phai goi mang tung ma
mot cho ca san (hang tram request, lam bot treo). Gio toan bo lich su gia
cua ca san nam trong MOT file (`data/market/ohlcv.parquet`), duoc cap nhat
dinh ky boi `scripts/backfill_data.py` (tai lan dau ~3 nam, cac lan sau chi
tai them vai phien moi va gop vao). Luc bot chay, moi noi can OHLCV toan san
(liquid_universe, screener, snapshot) CHI DOC file nay - khong goi mang.

`data/router.py::ohlcv()` van la duong lay gia CHO TUNG MA rieng le (vd
/khuyennghi mot ma) - no doc kho nay TRUOC, chi goi mang khi ma khong co
trong kho (xem router.py).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..config import get_paths
from ..logging_conf import get_logger

log = get_logger(__name__)

OHLCV_COLUMNS = ["symbol", "time", "open", "high", "low", "close", "volume"]
OHLCV_FILENAME = "ohlcv.parquet"
SYMBOLS_FILENAME = "symbols.parquet"

# Cache trong bo nho tien trinh: {duong_dan: (mtime_luc_doc, DataFrame)}. Tu
# lam moi khi file tren dia doi mtime (backfill_data.py ghi de file), khong
# can khoi dong lai tien trinh.
_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _market_dir() -> Path:
    d = get_paths().data_dir / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ohlcv_path() -> Path:
    return _market_dir() / OHLCV_FILENAME


def symbols_path() -> Path:
    return _market_dir() / SYMBOLS_FILENAME


def _read_cached(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    mtime = path.stat().st_mtime
    key = str(path)
    hit = _cache.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    frame = pd.read_parquet(path)
    _cache[key] = (mtime, frame)
    return frame


def load_ohlcv(symbols: list[str] | None = None, since: date | None = None) -> pd.DataFrame:
    """Doc OHLCV tu kho (toan san neu `symbols` la None). DataFrame RONG neu
    chua backfill lan nao - goi noi khong duoc tu dong goi mang bu vao."""
    frame = _read_cached(ohlcv_path(), OHLCV_COLUMNS)
    if frame.empty:
        return frame
    if symbols:
        wanted = {s.upper() for s in symbols}
        frame = frame[frame["symbol"].isin(wanted)]
    if since is not None:
        frame = frame[frame["time"] >= pd.Timestamp(since)]
    return frame.reset_index(drop=True)


def load_symbols() -> pd.DataFrame:
    """Danh sach ma + san niem yet (va cac cot khac neu co) tu kho."""
    return _read_cached(symbols_path(), ["symbol", "exchange"])


def frames_by_symbol(
    symbols: list[str] | None = None, since: date | None = None
) -> dict[str, pd.DataFrame]:
    """Tach OHLCV theo tung ma bang mot lan groupby - KHONG doc file nhieu lan."""
    frame = load_ohlcv(symbols, since)
    if frame.empty:
        return {}
    result: dict[str, pd.DataFrame] = {}
    for symbol, group in frame.groupby("symbol"):
        result[str(symbol)] = group.sort_values("time").reset_index(drop=True)
    return result


def last_updated() -> datetime | None:
    """Thoi diem file OHLCV duoc ghi lan gan nhat, None neu chua co kho."""
    path = ohlcv_path()
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime)


def save_ohlcv(frame: pd.DataFrame, merge: bool = True) -> int:
    """Ghi OHLCV vao kho, gop voi du lieu cu (neu `merge`) va khu trung theo
    (symbol, time), giu ban ghi MOI hon khi trung. Tra ve tong so dong sau khi ghi.
    """
    path = ohlcv_path()
    frame = frame[OHLCV_COLUMNS].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["time"] = pd.to_datetime(frame["time"])

    if merge and path.exists():
        existing = pd.read_parquet(path)
        frame = pd.concat([existing, frame], ignore_index=True)

    frame = frame.drop_duplicates(subset=["symbol", "time"], keep="last")
    frame = frame.sort_values(["symbol", "time"]).reset_index(drop=True)
    frame.to_parquet(path, index=False)
    _cache.pop(str(path), None)
    log.info("market_store: da ghi %d dong vao %s", len(frame), path)
    return len(frame)


def save_symbols(frame: pd.DataFrame) -> None:
    path = symbols_path()
    frame.to_parquet(path, index=False)
    _cache.pop(str(path), None)


def refresh(count_back: int = 10) -> int:
    """Cap nhat TANG DAN: tai `count_back` phien gan nhat cho CAC MA DA CO
    trong kho, gop vao (khu trung theo (symbol, time), giu ban ghi moi hon).

    Dung cho lich chay hang ngay (xem bot/scheduler.py, bot/main.py:
    daily_scan_job) - NGAN va nhanh hon nhieu so voi backfill lan dau. Neu
    kho chua co gi (chua chay scripts/backfill_data.py lan nao, hoac dia bi
    xoa trang - vd Render goi Free KHONG co dia luu ben vung, moi lan
    container khoi dong lai la kho lai rong), khong lam gi ca va tra ve 0 -
    goi noi (vd ensure_fresh_in_background()) tu quyet dinh co goi
    bootstrap() thay the hay khong.
    """
    existing = load_ohlcv()
    if existing.empty:
        log.warning(
            "market_store.refresh(): kho rong, chay scripts/backfill_data.py lan dau truoc"
        )
        return 0

    from .vietcap import fetch_ohlcv_bulk  # tranh import vong o muc module

    symbols = sorted(existing["symbol"].unique().tolist())
    frame = fetch_ohlcv_bulk(symbols, count_back=count_back)
    return save_ohlcv(frame, merge=True)


def bootstrap(exchanges: list[str] | None = None, count_back: int = 750) -> int:
    """Nap TOAN BO lich su gia cho CA SAN (giong scripts/backfill_data.py
    lan dau), dung khi kho HOAN TOAN RONG - vd container vua khoi dong tren
    moi truong khong co dia luu ben vung (Render goi Free: /data bi xoa
    trang moi lan container restart/spin-down-wake, khac voi may ca nhan).

    KHAC voi refresh(): refresh() chi tai bu vai phien cho ma DA CO san -
    tren kho rong no khong lam gi ca (dung y, tranh tu bia danh sach ma).
    bootstrap() moi thuc su tai danh sach ma + lich su day du tu dau.

    Cham hon refresh() nhieu (~2-3 phut cho toan san, do thuc te 1.523 ma/
    123s) - chi nen goi MOT LAN moi khi phat hien kho rong, khong goi lap
    lai moi vong quet dinh ky (xem analysis/snapshot.py:ensure_fresh_in_background()).
    """
    from ..config import get_settings
    from .vietcap import fetch_all_symbols, fetch_ohlcv_bulk  # tranh import vong

    exchanges = exchanges or get_settings().get(
        "universe.exchanges", ["HOSE", "HNX", "UPCOM"]
    )
    symbols_frame = fetch_all_symbols(exchanges)
    if symbols_frame.empty:
        log.warning("market_store.bootstrap(): khong lay duoc danh sach ma, bo qua")
        return 0
    save_symbols(symbols_frame)

    symbols = symbols_frame["symbol"].tolist()
    frame = fetch_ohlcv_bulk(symbols, count_back=count_back)
    total = save_ohlcv(frame, merge=False)
    log.info("market_store.bootstrap(): %d ma, %d dong", len(symbols), total)
    return total
