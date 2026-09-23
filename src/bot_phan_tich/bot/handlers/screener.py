"""Lenh /loc (/screen): loc co phieu, co nut bam cho ba bo loc dung san,
va tham so tuy chinh dang `/loc san=HOSE kn=MUA rsi=quaban`.
"""
from __future__ import annotations

import asyncio
from html import escape

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
from ...analysis.snapshot import data_unavailable_message, load_snapshot
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


async def _no_data_text() -> str | None:
    """Thong bao (da escape HTML) neu chua co snapshot - noi ro dang nap den
    dau hoac lan truoc loi gi. None neu da co du lieu."""
    if not (await asyncio.to_thread(load_snapshot)).empty:
        return None
    return escape(data_unavailable_message())


@router.message(Command("loc", "screen"))
async def cmd_screen(message: Message) -> None:
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

    no_data = await _no_data_text()
    if no_data:
        await message.answer(no_data)
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

    preset_key = callback.data.split(":", 1)[1]
    factory = _PRESETS.get(preset_key)
    if factory is None:
        await callback.answer("Bộ lọc không hợp lệ.")
        return

    # Gui thanh tin nhan thuong, khong dung show_alert: popup cua Telegram gioi
    # han 200 ky tu, khong du cho thong bao tien do/loi.
    no_data = await _no_data_text()
    if no_data:
        await callback.answer()
        await callback.message.answer(no_data)
        return

    await callback.answer("Đang lọc...")
    try:
        report = await asyncio.to_thread(screen_report, factory())
        text = screener_results_card(report.results, note=report.note)
    except Exception as exc:
        log.exception("Loc theo bo dung san %s that bai", preset_key)
        text = error_card(str(exc))
    await callback.message.answer(text)
