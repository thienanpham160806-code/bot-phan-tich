"""Tinh san khuyen nghi CUOI NGAY cho toan bo vu tru thanh khoan.

Giai quyet van de: chi bao ky thuat theo ngay KHONG DOI trong pham vi mot
phien, nen /loc va /tinhieu khong can tinh lai moi lan nguoi dung bam nut -
chi can TRA BANG mot snapshot da tinh san MOT LAN sau gio dong cua.

build_snapshot() goi analysis.scoring.recommend() DUNG MOT LAN cho moi ma -
recommend() da tu tinh macd_state/rsi_state/ichimoku_state/divergence/
volume_ratio va tra kem theo trong Recommendation, KHONG tinh lai o day
(xem analysis/scoring.py). Chay song song bang ProcessPoolExecutor vi day
la cong viec nang CPU (tinh chi bao tren hang tram DataFrame).
"""
from __future__ import annotations

import asyncio
import os
import time as time_module
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from datetime import time as dt_time

import pandas as pd

from ..config import get_paths
from ..data import market_store
from ..data.universe import liquid_universe
from ..logging_conf import get_logger
from .scoring import recommend

log = get_logger(__name__)

SNAPSHOT_FILENAME = "snapshot.parquet"
_MIN_BARS = 60
_MARKET_CLOSE_CUTOFF = dt_time(15, 10)  # trung voi bot.scan_cron mac dinh


def snapshot_path():
    d = get_paths().data_dir / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d / SNAPSHOT_FILENAME


def _evaluate_one(symbol: str, exchange: str | None) -> dict | None:
    """Chay trong TIEN TRINH CON (ProcessPoolExecutor) - tu doc du lieu tu
    market_store (khong truyen DataFrame lon qua ranh gioi tien trinh).
    Tra None neu thieu du lieu hoac loi - khong lam hong ca lot tinh.
    """
    frame = market_store.load_ohlcv([symbol])
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


def build_snapshot(
    symbols: list[str] | None = None, max_workers: int | None = None
) -> pd.DataFrame:
    """Tinh khuyen nghi cho toan bo `symbols` (mac dinh: liquid_universe()),
    ghi ra snapshot.parquet. Tra ve chinh DataFrame vua ghi.
    """
    symbols = symbols if symbols is not None else liquid_universe()
    if not symbols:
        log.warning("build_snapshot: vu tru rong (chua backfill?), khong tinh gi")
        return pd.DataFrame()

    symbols_meta = market_store.load_symbols()
    exchange_map: dict[str, str] = {}
    if not symbols_meta.empty and "exchange" in symbols_meta.columns:
        exchange_map = dict(zip(symbols_meta["symbol"], symbols_meta["exchange"], strict=False))

    max_workers = max_workers or max(1, (os.cpu_count() or 2) - 1)
    started = time_module.time()
    rows: list[dict] = []
    failed = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_evaluate_one, s, exchange_map.get(s)): s for s in symbols}
        done = 0
        for future in as_completed(futures):
            symbol = futures[future]
            done += 1
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                log.warning("build_snapshot: loi tien trinh con cho %s: %s", symbol, exc)
                row = None
            if row is not None:
                rows.append(row)
            else:
                failed += 1
            if done % 100 == 0 or done == len(symbols):
                log.info("build_snapshot: %d/%d ma (%d bi bo qua)", done, len(symbols), failed)

    frame = pd.DataFrame(rows)
    elapsed = time_module.time() - started
    log.info(
        "build_snapshot: %d/%d ma thanh cong trong %.1fs", len(rows), len(symbols), elapsed
    )

    frame.to_parquet(snapshot_path(), index=False)
    return frame


def load_snapshot() -> pd.DataFrame:
    path = snapshot_path()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def snapshot_last_updated() -> datetime | None:
    path = snapshot_path()
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime)


def last_expected_session(now: datetime | None = None) -> date:
    """Ngay lam viec gan nhat MA snapshot LE RA phai co du lieu, tinh tu
    `now`. Xap xi don gian (khong tinh ngay le) dua tren gio dong cua
    `_MARKET_CLOSE_CUTOFF` va cuoi tuan - du dung de canh bao "du lieu cu",
    khong doi hoi chinh xac tuyet doi.
    """
    now = now or datetime.now()
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
    """Neu snapshot thieu hoac cu hon phien gan nhat: cap nhat kho
    (data/market_store.py:refresh()) roi dung lai snapshot, CHAY O NEN
    (asyncio.to_thread) - KHONG chan bot luc khoi dong. Goi tu bot/main.py
    nhu mot task nen (asyncio.create_task), khong await truc tiep trong luong
    khoi dong chinh.
    """
    global _build_in_progress
    if not is_stale():
        return

    from ..data import market_store  # tranh import vong o muc module

    _build_in_progress = True
    log.info("ensure_fresh_in_background: snapshot cu/thieu, dang cap nhat o nen...")
    try:
        updated_rows = await asyncio.to_thread(market_store.refresh)
        log.info("ensure_fresh_in_background: market_store.refresh() -> %d dong", updated_rows)
        frame = await asyncio.to_thread(build_snapshot)
        log.info("ensure_fresh_in_background: build_snapshot() -> %d ma", len(frame))
    except Exception:
        log.exception("ensure_fresh_in_background: that bai")
    finally:
        _build_in_progress = False
