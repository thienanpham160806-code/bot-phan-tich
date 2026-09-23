"""Lenh /tinhieu (/signals): tin hieu MUA/TICH LUY va BAN/GIAM TY TRONG cua
phien gan nhat - yeu cau con thieu cua de (xem PHAN 5).

CHI DOC snapshot da tinh san (xem analysis/screener.py:today_signals()),
cung nguyen tac voi /loc - khong tinh lai, khong goi mang, xong duoi 1 giay.
"""
from __future__ import annotations

import asyncio
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...analysis.screener import today_signals
from ...analysis.snapshot import data_unavailable_message, load_snapshot
from ...logging_conf import get_logger
from ..formatters import error_card, signals_card

log = get_logger(__name__)
router = Router(name="signals")


@router.message(Command("tinhieu", "signals"))
async def cmd_signals(message: Message) -> None:
    if (await asyncio.to_thread(load_snapshot)).empty:
        # Noi ro dang nap den dau / lan truoc loi gi, khong chi "dang chuan bi".
        await message.answer(escape(data_unavailable_message()))
        return

    try:
        report = await asyncio.to_thread(today_signals)
        text = signals_card(report)
    except Exception as exc:
        log.exception("Lenh /tinhieu that bai")
        text = error_card(str(exc))
    await message.answer(text)
