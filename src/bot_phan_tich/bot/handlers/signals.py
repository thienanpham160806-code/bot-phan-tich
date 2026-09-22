"""Lenh /tinhieu (/signals): tin hieu MUA/TICH LUY va BAN/GIAM TY TRONG cua
phien gan nhat - yeu cau con thieu cua de (xem PHAN 5).

CHI DOC snapshot da tinh san (xem analysis/screener.py:today_signals()),
cung nguyen tac voi /loc - khong tinh lai, khong goi mang, xong duoi 1 giay.
"""
from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...analysis.screener import today_signals
from ...analysis.snapshot import is_build_in_progress
from ...logging_conf import get_logger
from ..formatters import error_card, signals_card

log = get_logger(__name__)
router = Router(name="signals")

_PREPARING_MESSAGE = (
    "⏳ Đang chuẩn bị dữ liệu cho phiên này (cập nhật kho giá + tính lại khuyến nghị "
    "toàn sàn). Vui lòng thử lại sau vài phút."
)


@router.message(Command("tinhieu", "signals"))
async def cmd_signals(message: Message) -> None:
    if is_build_in_progress():
        await message.answer(_PREPARING_MESSAGE)
        return

    try:
        report = await asyncio.to_thread(today_signals)
        text = signals_card(report)
    except Exception as exc:
        log.exception("Lenh /tinhieu that bai")
        text = error_card(str(exc))
    await message.answer(text)
