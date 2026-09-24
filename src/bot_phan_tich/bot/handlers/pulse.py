"""Lenh /biendong (/pulse): bien dong thi truong va tac dong len cac ma dang
theo doi. `/biendong on|off` bat/tat ban tin tu dong trong phien (lich o
config/settings.yaml: bot.market_pulse_crons, gui tu bot/main.py).
"""
from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...alerts import watchlist as watchlist_store
from ...analysis.market_pulse import build_market_pulse, default_watchlist
from ...data.cache import set_pulse_subscriber
from ...logging_conf import get_logger
from ..formatters import error_card, market_pulse_card, run_with_notice

log = get_logger(__name__)
router = Router(name="pulse")


def watched_for_chat(chat_id: int) -> tuple[list[str], bool]:
    """(danh sach ma cua chat, co dang dung danh sach mac dinh khong). Chat
    chua /sub ma nao - hoac danh sach vua mat do Render Free khoi dong lai -
    dung danh sach theo doi mac dinh trong config/universe.yaml."""
    symbols = watchlist_store.list_symbols(chat_id)
    if symbols:
        return symbols, False
    return default_watchlist(), True


@router.message(Command("biendong", "pulse"))
async def cmd_pulse(message: Message) -> None:
    parts = (message.text or "").split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    chat_id = message.chat.id

    if arg in ("on", "bat", "start"):
        set_pulse_subscriber(chat_id, True)
        await message.answer(
            "🔔 <b>Đã BẬT bản tin biến động thị trường tự động.</b>\n\n"
            "Bot gửi trong các phiên giao dịch (mặc định 11:35 hết phiên sáng và "
            "14:50 sau ATC): VN-Index, độ rộng, khối ngoại và tác động lên các mã "
            "bạn theo dõi.\n\n"
            f"<i>Trên Render gói Free, đăng ký mất khi bot khởi động lại. Để giữ "
            f"cố định, thêm biến <code>AUTO_SUBSCRIBE_CHAT_IDS={chat_id}</code> "
            f"(chat id của bạn) trong tab Environment của Render.</i>"
        )
        return
    if arg in ("off", "tat", "stop"):
        set_pulse_subscriber(chat_id, False)
        await message.answer("🔕 <b>Đã TẮT bản tin biến động thị trường tự động.</b>")
        return

    symbols, using_default = watched_for_chat(chat_id)

    async def _work() -> str:
        pulse = await asyncio.to_thread(build_market_pulse, symbols)
        return market_pulse_card(pulse, symbols, using_default=using_default)

    try:
        await run_with_notice(message, _work)
    except Exception as exc:
        log.exception("Lenh /biendong that bai")
        await message.answer(error_card(str(exc)))
