"""Tinh san khuyen nghi CUOI NGAY cho toan bo vu tru thanh khoan.

Giai quyet van de: chi bao ky thuat theo ngay KHONG DOI trong pham vi mot
phien, nen /loc va /tinhieu khong can tinh lai moi lan nguoi dung bam nut -
chi can TRA BANG mot snapshot da tinh san MOT LAN sau gio dong cua.

build_snapshot() goi analysis.scoring.recommend() DUNG MOT LAN cho moi ma -
recommend() da tu tinh macd_state/rsi_state/ichimoku_state/divergence/
volume_ratio va tra kem theo trong Recommendation, KHONG tinh lai o day
(xem analysis/scoring.py).

Doc kho DUNG MOT LAN o tien trinh chinh (market_store.frames_by_symbol), roi
duyet TUAN TU. Khong dung da tien trinh: ban cu dung ProcessPoolExecutor voi
max(1, os.cpu_count() - 1) tien trinh con, MOI tien trinh tu doc lai TOAN BO
kho (~111 MB) - tren container, os.cpu_count() tra so core may chu vat ly
(khong phai han muc CPU duoc cap), nen de dang vuot 512 MB cua Render goi
Free -> OOM kill -> mat dia tam -> nap lai -> lap vo tan. Do thuc te
recommend() chi mat ~15 ms/ma, 700 ma ~ 11 giay tren MOT luong - da tien
trinh khong dang voi chi phi RAM. Van cho phep ThreadPoolExecutor qua
config `snapshot.max_workers` (mac dinh 1).
"""
from __future__ import annotations

import asyncio
import time as time_module
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from datetime import time as dt_time

import pandas as pd

from ..config import bot_timezone, get_paths, get_settings
from ..data import fundamentals_store, market_store
from ..data.universe import liquid_universe
from ..logging_conf import get_logger
from ..sysinfo import format_mb, peak_rss_mb
from .scoring import recommend

log = get_logger(__name__)

SNAPSHOT_FILENAME = "snapshot.parquet"
_MIN_BARS = 60
_MARKET_CLOSE_CUTOFF = dt_time(15, 10)  # trung voi bot.scan_cron mac dinh
_PROGRESS_EVERY = 200


def snapshot_path():
    d = get_paths().data_dir / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d / SNAPSHOT_FILENAME


def _evaluate_one(symbol: str, exchange: str | None, frame: pd.DataFrame) -> dict | None:
    """Tinh mot dong snapshot tu DataFrame gia CUA RIENG ma nay (da doc san o
    build_snapshot, khong tu doc lai kho). Tra None neu thieu du lieu hoac
    loi - khong lam hong ca lot tinh.
    """
    if len(frame) < _MIN_BARS:
        return None
    try:
        rec = recommend(frame, symbol)
    except Exception as exc:  # noqa: BLE001 - ghi log, bo qua ma nay, khong lan ca lot
        log.warning("build_snapshot: bo qua %s do loi: %s", symbol, exc)
        return None

    close_series = frame["close"]
    prev_close = float(close_series.iloc[-2]) if len(close_series) > 1 else rec.close
    change_pct = (rec.close / prev_close - 1) if prev_close else None

    macd_st, rsi_st, ichi_st = rec.macd_state, rec.rsi_state, rec.ichimoku_state
    tk_cross = ichi_st.get("tk_cross") or (None, None, None)

    return {
        "symbol": symbol,
        "exchange": exchange,
        "close": rec.close,
        "change_pct": change_pct,
        "volume": float(frame["volume"].iloc[-1]),
        "vol_ratio20": rec.volume_ratio,
        "action": rec.action,
        "total_score": rec.total_score,
        "score_macd": rec.component_scores.get("macd"),
        "score_rsi": rec.component_scores.get("rsi"),
        "score_ichimoku": rec.component_scores.get("ichimoku"),
        "price_vs_kumo": ichi_st.get("price_vs_kumo"),
        "kumo_break_bars": ichi_st.get("kumo_break_bars"),
        "kumo_thickness": ichi_st.get("kumo_thickness"),
        "macd_cross": macd_st.get("cross"),
        "macd_bars_since": macd_st.get("bars_since_cross"),
        "macd_above_zero": macd_st.get("above_zero"),
        "rsi": rsi_st.get("value"),
        "rsi_zone": rsi_st.get("zone"),
        "rsi_upper": rsi_st.get("upper"),
        "rsi_lower": rsi_st.get("lower"),
        "divergence_type": rec.divergence.get("type"),
        "tk_cross": tk_cross[0],
        "stop_loss": rec.stop_loss,
        "target": rec.target,
        "reasons": list(rec.reasons),
        "as_of": frame["time"].iloc[-1],
    }


def _safe_evaluate(task: tuple[str, str | None, pd.DataFrame | None]) -> dict | None:
    symbol, exchange, frame = task
    if frame is None:
        return None
    try:
        return _evaluate_one(symbol, exchange, frame)
    except Exception as exc:  # noqa: BLE001 - mot ma loi khong duoc lam hong ca lot
        log.warning("build_snapshot: bo qua %s do loi: %s", symbol, exc)
        return None


def build_snapshot(
    symbols: list[str] | None = None, max_workers: int | None = None
) -> pd.DataFrame:
    """Tinh khuyen nghi cho toan bo `symbols` (mac dinh: liquid_universe()),
    ghi ra snapshot.parquet. Tra ve chinh DataFrame vua ghi.

    Doc kho MOT LAN (frames_by_symbol), duyet tuan tu - RAM them toi da ~mot
    ban sao kho gia (cac DataFrame theo tung ma). `max_workers` > 1 (hoac
    config `snapshot.max_workers`) thi dung ThreadPoolExecutor, van chung
    mot tien trinh, khong nhan ban kho.
    """
    symbols = symbols if symbols is not None else liquid_universe()
    if not symbols:
        log.warning("build_snapshot: vu tru rong (chua backfill?), khong tinh gi")
        return pd.DataFrame()

    symbols_meta = market_store.load_symbols()
    exchange_map: dict[str, str] = {}
    if not symbols_meta.empty and "exchange" in symbols_meta.columns:
        exchange_map = dict(zip(symbols_meta["symbol"], symbols_meta["exchange"], strict=False))

    frames = market_store.frames_by_symbol(symbols)
    tasks = [(s, exchange_map.get(s), frames.get(s)) for s in symbols]
    workers = max_workers or int(get_settings().get("snapshot.max_workers", 1))

    started = time_module.time()
    rows: list[dict] = []
    failed = 0
    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    results = executor.map(_safe_evaluate, tasks) if executor else map(_safe_evaluate, tasks)
    try:
        for done, row in enumerate(results, start=1):
            if row is not None:
                rows.append(row)
            else:
                failed += 1
            if done % _PROGRESS_EVERY == 0 or done == len(tasks):
                log.info(
                    "build_snapshot: %d/%d ma (%d bi bo qua), RAM dinh %s",
                    done, len(tasks), failed, format_mb(peak_rss_mb()),
                )
    finally:
        if executor is not None:
            executor.shutdown()

    frame = pd.DataFrame(rows)
    elapsed = time_module.time() - started
    log.info(
        "build_snapshot: %d/%d ma thanh cong trong %.1fs", len(rows), len(symbols), elapsed
    )

    frame = _merge_fundamentals(frame)
    frame.to_parquet(snapshot_path(), index=False)
    return frame


def _merge_fundamentals(frame: pd.DataFrame) -> pd.DataFrame:
    """Gop cot pe/pb/roe tu data/fundamentals_store.py neu kho da co (chay
    scripts/backfill_fundamentals.py truoc). Ma nao khong co trong kho fundamentals
    (chua backfill, hoac nguon khong tra duoc) se la NaN - screener.py tu bo qua
    dieu kien loc theo fundamentals cho ma do, KHONG bia so."""
    fundamentals = fundamentals_store.load_fundamentals()
    if fundamentals.empty:
        return frame
    return frame.merge(
        fundamentals[["symbol", "pe", "pb", "roe"]], on="symbol", how="left"
    )


def load_snapshot() -> pd.DataFrame:
    path = snapshot_path()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def snapshot_last_updated() -> datetime | None:
    """Thoi diem ghi snapshot, CO gan mui gio bot.timezone (khong phu thuoc
    mui gio cua may chu)."""
    path = snapshot_path()
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=bot_timezone())


def _as_local(now: datetime | None) -> datetime:
    """Quy `now` ve gio bot.timezone. Gio khong gan mui gio duoc coi la DA la
    gio dia phuong cua bot (khong phai gio may chu)."""
    tz = bot_timezone()
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def last_expected_session(now: datetime | None = None) -> date:
    """Ngay lam viec gan nhat MA snapshot LE RA phai co du lieu, tinh tu
    `now`. Xap xi don gian (khong tinh ngay le) dua tren gio dong cua
    `_MARKET_CLOSE_CUTOFF` va cuoi tuan - du dung de canh bao "du lieu cu",
    khong doi hoi chinh xac tuyet doi.

    Tinh theo gio bot.timezone (Viet Nam), KHONG theo gio may chu: Render
    chay UTC, lech 7 gio - neu dung datetime.now() tran thi 15h30 gio VN
    (08h30 UTC) bi coi la "truoc gio dong cua".
    """
    now = _as_local(now)
    d = now.date()
    if now.weekday() >= 5 or now.time() < _MARKET_CLOSE_CUTOFF:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def is_stale(now: datetime | None = None) -> bool:
    """True neu chua co snapshot, hoac snapshot cu hon phien giao dich gan nhat."""
    updated = snapshot_last_updated()
    if updated is None:
        return True
    return updated.date() < last_expected_session(now)


# ------------------------------------------------------ dung nen luc bot khoi dong
_build_in_progress = False


def is_build_in_progress() -> bool:
    """True trong luc ensure_fresh_in_background() dang chay - dung de handler
    /loc, /tinhieu hien thong bao "dang chuan bi du lieu" thay vi doc snapshot cu."""
    return _build_in_progress


async def ensure_fresh_in_background() -> None:
    """Neu snapshot thieu hoac cu hon phien gan nhat: cap nhat kho roi dung
    lai snapshot, CHAY O NEN (asyncio.to_thread) - KHONG chan bot luc khoi
    dong. Goi tu bot/main.py nhu mot task nen (asyncio.create_task), khong
    await truc tiep trong luong khoi dong chinh.

    Kho HOAN TOAN RONG (vd container Render goi Free khong co dia luu ben
    vung, moi lan restart la mat sach data/) can market_store.bootstrap()
    (nap toan bo, ~2-3 phut) thay vi refresh() (chi tai bu cho ma DA CO,
    tren kho rong se khong lam gi ca - xem market_store.py). Neu khong phan
    biet hai truong hop nay, bot deploy tren moi truong dia tam se MAI MAI
    khong co du lieu toan san (/loc, /tinhieu luon "dang chuan bi du lieu",
    /khuyennghi cho mot ma bat ky phai goi mang truc tiep moi lan - CHAM).
    """
    global _build_in_progress
    if not is_stale():
        return

    from ..data import market_store  # tranh import vong o muc module

    _build_in_progress = True
    log.info("ensure_fresh_in_background: snapshot cu/thieu, dang cap nhat o nen...")
    try:
        if market_store.load_ohlcv().empty:
            updated_rows = await asyncio.to_thread(market_store.bootstrap)
            log.info(
                "ensure_fresh_in_background: market_store.bootstrap() -> %d dong", updated_rows
            )
        else:
            updated_rows = await asyncio.to_thread(market_store.refresh)
            log.info(
                "ensure_fresh_in_background: market_store.refresh() -> %d dong", updated_rows
            )
        frame = await asyncio.to_thread(build_snapshot)
        log.info("ensure_fresh_in_background: build_snapshot() -> %d ma", len(frame))
    except Exception:
        log.exception("ensure_fresh_in_background: that bai")
    finally:
        _build_in_progress = False
