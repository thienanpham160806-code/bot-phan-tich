"""Lenh /trangthai (/status): tinh trang du lieu cua bot - cong cu cham bai va
go loi. Ai go cung duoc (khong gioi han admin).

Chi doc metadata/cot nho, KHONG nap ca kho gia vao RAM chi de dem.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...analysis import snapshot
from ...data import fundamentals_store, market_store
from ...logging_conf import get_logger
from ...sysinfo import current_rss_mb, peak_rss_mb
from ..formatters import error_card, status_card

log = get_logger(__name__)
router = Router(name="status")


@dataclass
class SystemStatus:
    store_symbols: int
    store_rows: int
    store_updated: datetime | None
    store_size_mb: float | None
    snapshot_symbols: int
    snapshot_updated: datetime | None
    snapshot_stale: bool
    snapshot_partial: bool
    fundamentals_symbols: int
    fundamentals_updated: datetime | None
    build: snapshot.BuildStatus
    progress: str | None
    ram_mb: float | None
    ram_peak_mb: float | None


def collect_system_status() -> SystemStatus:
    store_path = market_store.ohlcv_path()
    symbols = market_store.load_ohlcv(columns=["symbol"])
    snap = snapshot.load_snapshot()
    fundamentals = fundamentals_store.load_fundamentals()
    return SystemStatus(
        store_symbols=int(symbols["symbol"].nunique()) if not symbols.empty else 0,
        store_rows=len(symbols),
        store_updated=market_store.last_updated(),
        store_size_mb=store_path.stat().st_size / 1_048_576 if store_path.exists() else None,
        snapshot_symbols=len(snap),
        snapshot_updated=snapshot.snapshot_last_updated(),
        snapshot_stale=snapshot.is_stale(),
        snapshot_partial=snapshot.is_partial_snapshot(),
        fundamentals_symbols=len(fundamentals),
        fundamentals_updated=fundamentals_store.fundamentals_last_updated(),
        build=snapshot.get_build_status(),
        progress=snapshot.progress_text(),
        ram_mb=current_rss_mb(),
        ram_peak_mb=peak_rss_mb(),
    )


@router.message(Command("trangthai", "status"))
async def cmd_status(message: Message) -> None:
    try:
        status = await asyncio.to_thread(collect_system_status)
        text = status_card(status)
    except Exception as exc:
        log.exception("Lenh /trangthai that bai")
        text = error_card(str(exc))
    await message.answer(text)
