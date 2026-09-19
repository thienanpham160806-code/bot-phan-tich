"""Lenh /loc (/screen): loc co phieu, co nut bam cho ba bo loc dung san."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...analysis.screener import preset_accumulate, preset_breakout, preset_warning, screen_report
from ...logging_conf import get_logger
from ..formatters import error_card, screener_results_card
from ..keyboards import screener_menu

log = get_logger(__name__)
router = Router(name="screener")

_PRESETS = {
    "breakout": preset_breakout,
    "accumulate": preset_accumulate,
    "warning": preset_warning,
}


@router.message(Command("loc", "screen"))
async def cmd_screen(message: Message) -> None:
    await message.answer(
        "Chọn một bộ lọc dựng sẵn bên dưới. Lọc theo điều kiện tuỳ chỉnh "
        "(P/E, P/B, ROE...) sẽ được bổ sung ở phiên bản sau.",
        reply_markup=screener_menu(),
    )


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("screen:"))
async def on_screen_preset(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    preset_key = callback.data.split(":", 1)[1]
    factory = _PRESETS.get(preset_key)
    if factory is None:
        await callback.answer("Bộ lọc không hợp lệ.")
        return

    await callback.answer("Đang quét...")
    try:
        report = screen_report(factory())
        text = screener_results_card(report.results, note=report.note)
    except Exception as exc:
        log.exception("Loc theo bo dung san %s that bai", preset_key)
        text = error_card(str(exc))
    await callback.message.answer(text)
