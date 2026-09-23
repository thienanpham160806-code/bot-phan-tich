"""Lenh /trangthai (/status): tinh trang du lieu cua bot - cong cu cham bai va
go loi. Ai go cung duoc (khong gioi han admin).

`/trangthai chandoan` chay them cac kiem tra cua scripts/diagnose.py (RAM/CPU
that cua container, goi thu Vietcap/DNSE) - cach duy nhat de chan doan tren
Render goi Free, vi goi nay khong co Shell.
"""
from __future__ import annotations

import asyncio
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...diagnostics import collect_system_status, format_table, run_diagnostics
from ...logging_conf import get_logger
from ..formatters import error_card, status_card

log = get_logger(__name__)
router = Router(name="status")

_DIAGNOSE_ARGS = {"chandoan", "chẩnđoán", "full", "diagnose"}


@router.message(Command("trangthai", "status"))
async def cmd_status(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    wants_diagnose = len(args) > 1 and args[1].strip().lower().replace(" ", "") in _DIAGNOSE_ARGS
    try:
        if wants_diagnose:
            await message.answer("🔎 Đang chẩn đoán (gọi thử các nguồn dữ liệu, vài giây)...")
            checks = await asyncio.to_thread(run_diagnostics)
            text = f"<pre>{escape(format_table(checks))}</pre>"
        else:
            text = status_card(await asyncio.to_thread(collect_system_status))
    except Exception as exc:
        log.exception("Lenh /trangthai that bai")
        text = error_card(str(exc))
    await message.answer(text)
