"""Lenh /tracuu (/info): ho so + chi so chinh + cap nhat gan day cho mot ma."""
from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...analysis.lookup import lookup
from ...logging_conf import get_logger
from ..formatters import error_card, lookup_card, run_with_notice
from .common import parse_symbol

log = get_logger(__name__)
router = Router(name="lookup")


@router.message(Command("tracuu", "info"))
async def cmd_lookup(message: Message) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer("Cú pháp: <code>/tracuu FPT</code>")
        return

    async def work() -> str:
        try:
            profile = await asyncio.to_thread(lookup, symbol)
            return lookup_card(profile)
        except Exception as exc:
            log.exception("Lenh /tracuu that bai cho %s", symbol)
            return error_card(str(exc))

    await run_with_notice(message, work)
