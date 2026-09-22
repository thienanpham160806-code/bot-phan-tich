"""Lenh /loc (/screen): loc co phieu, co nut bam cho ba bo loc dung san,
va tham so tuy chinh dang `/loc san=HOSE kn=MUA rsi=quaban`.
"""
from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...analysis.screener import (
    CriteriaParseError,
    parse_criteria,
    preset_accumulate,
    preset_breakout,
    preset_warning,
    screen_report,
)
from ...analysis.snapshot import is_build_in_progress, load_snapshot
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


_PREPARING_MESSAGE = (
    "⏳ Đang chuẩn bị dữ liệu cho phiên này (cập nhật kho giá + tính lại khuyến nghị "
    "toàn sàn). Vui lòng thử lại sau vài phút."
)


@router.message(Command("loc", "screen"))
async def cmd_screen(message: Message) -> None:
    if is_build_in_progress() and load_snapshot().empty:
        await message.answer(_PREPARING_MESSAGE)
        return

    args = (message.text or "").split(maxsplit=1)
    custom_args = args[1].strip() if len(args) > 1 else ""

    if not custom_args:
        intro_text = (
            "🔍 <b>BỘ LỌC CỔ PHIẾU TOÀN SÀN</b>\n\n"
            "Chọn một bộ lọc dựng sẵn bên dưới:\n"
            "• 🚀 <b>Đột phá:</b> Vượt mây Kumo + MACD cắt lên + Khối lượng nổ (>= 1.5x TB20)\n"
            "• 📦 <b>Tích luỹ:</b> Nén giá trong mây mỏng + RSI trung tính + Von cạn kiệt\n"
            "• ⚠️ <b>Cảnh báo:</b> Giá vừa thủng mây Kumo hoặc xuất hiện phân kỳ âm\n\n"
            "Hoặc gõ điều kiện tuỳ chỉnh, ví dụ:\n"
            "• <code>/loc san=HOSE kn=MUA</code> (Lọc các mã có khuyến nghị MUA trên HOSE)\n"
            "• <code>/loc san=HOSE kn=tichluy</code> (Lọc các mã tích luỹ nền giá)\n"
            "• <code>/loc may=tren kl=1.2</code> (Giá trên mây, khối lượng tăng > 1.2 lần)\n"
            "• <code>/loc rsi=quaban</code> (RSI rơi vào vùng quá bán để canh bắt đáy)"
        )
        await message.answer(intro_text, reply_markup=screener_menu())
        return

    try:
        criteria = parse_criteria(custom_args)
    except CriteriaParseError as exc:
        await message.answer(error_card(str(exc)))
        return

    try:
        report = await asyncio.to_thread(screen_report, criteria)
        text = screener_results_card(report.results, note=report.note)
    except Exception as exc:
        log.exception("Lenh /loc (tuy chinh) that bai")
        text = error_card(str(exc))
    await message.answer(text)


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("screen:"))
async def on_screen_preset(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return

    if is_build_in_progress() and load_snapshot().empty:
        await callback.answer("Đang chuẩn bị dữ liệu, thử lại sau vài phút.", show_alert=True)
        return

    preset_key = callback.data.split(":", 1)[1]
    factory = _PRESETS.get(preset_key)
    if factory is None:
        await callback.answer("Bộ lọc không hợp lệ.")
        return

    await callback.answer("Đang lọc...")
    try:
        report = await asyncio.to_thread(screen_report, factory())
        text = screener_results_card(report.results, note=report.note)
    except Exception as exc:
        log.exception("Loc theo bo dung san %s that bai", preset_key)
        text = error_card(str(exc))
    await callback.message.answer(text)
