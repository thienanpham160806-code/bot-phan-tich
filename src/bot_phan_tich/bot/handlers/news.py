"""Xu ly lenh tong hop tin tuc thi truong, nghi dinh, nghi quyet: /tintuc."""
from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...data.cache import (
    get_recent_macro_news,
    is_news_subscribed,
    save_macro_news_items,
    set_news_subscriber,
)
from ...data.macro_news import fetch_all_macro_news
from ...logging_conf import get_logger
from ..formatters import error_card, macro_news_card, run_with_notice

log = get_logger(__name__)
router = Router(name="news")


def _build_news_keyboard(chat_id: int, current_cat: str | None = None) -> InlineKeyboardMarkup:
    """Tao ban phim inline dieu khien xem tin tuc va bat/tat dang ky."""
    subbed = is_news_subscribed(chat_id)
    toggle_text = "🔕 Tắt nhận tin 1h" if subbed else "🔔 Bật nhận tin 1h"
    toggle_data = "news:toggle"

    row1 = [InlineKeyboardButton(text=toggle_text, callback_data=toggle_data)]

    cat_policy = "🏛️ [Chính sách]" if current_cat == "CHÍNH SÁCH - PHÁP LUẬT" else "🏛️ Chính sách"
    cat_macro = "📊 [Vĩ mô & TTCK]" if current_cat == "VĨ MÔ & THỊ TRƯỜNG" else "📊 Vĩ mô & TTCK"

    row2 = [
        InlineKeyboardButton(
            text=cat_policy,
            callback_data="news:cat:CHÍNH SÁCH - PHÁP LUẬT",
        ),
        InlineKeyboardButton(
            text=cat_macro,
            callback_data="news:cat:VĨ MÔ & THỊ TRƯỜNG",
        ),
    ]

    row3 = [
        InlineKeyboardButton(text="🌐 Tất cả tin", callback_data="news:cat:ALL"),
        InlineKeyboardButton(text="🔄 Làm mới", callback_data="news:refresh"),
    ]

    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3])


def _load_or_refresh_news(category: str | None = None, limit: int = 6) -> list[dict]:
    """Doc tu CSDL hoac tai moi tu RSS neu CSDL trong."""
    items = get_recent_macro_news(limit=limit, category=category)
    if not items:
        raw_items = fetch_all_macro_news()
        dict_items = [it.to_dict() for it in raw_items]
        save_macro_news_items(dict_items)
        items = get_recent_macro_news(limit=limit, category=category)
    return items


@router.message(Command("tintuc", "news"))
async def cmd_news(message: Message) -> None:
    text = (message.text or "").strip()
    parts = text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""

    chat_id = message.chat.id

    if arg in ("on", "bat", "start"):
        set_news_subscriber(chat_id, True)
        await message.answer(
            "🔔 <b>Đã BẬT nhận bản tin tự động mỗi 1 giờ!</b>\n\n"
            "Bot sẽ tự động tổng hợp tin tức vĩ mô, văn bản quy phạm pháp luật, "
            "nghị định và nghị quyết mới nhất gửi đến bạn định kỳ mỗi tiếng.\n\n"
            "<i>Trên Render gói Free, đăng ký mất khi bot khởi động lại. Để giữ cố "
            f"định, thêm biến <code>AUTO_SUBSCRIBE_CHAT_IDS={chat_id}</code> (chat id "
            "của bạn) trong tab Environment của Render.</i>",
            reply_markup=_build_news_keyboard(chat_id),
        )
        return

    if arg in ("off", "tat", "stop"):
        set_news_subscriber(chat_id, False)
        await message.answer(
            "🔕 <b>Đã TẮT nhận bản tin tự động mỗi 1 giờ.</b>\n\n"
            "Bạn có thể gõ <code>/tintuc</code> bất kỳ lúc nào để xem tin tức cập nhật tức thì.",
            reply_markup=_build_news_keyboard(chat_id),
        )
        return

    cat_filter: str | None = None
    title_suffix = "Mới Nhất"
    if arg in ("luat", "nghidinh", "chinhsach"):
        cat_filter = "CHÍNH SÁCH - PHÁP LUẬT"
        title_suffix = "Chính Sách & Nghị Định"
    elif arg in ("vimo", "ttck", "chungkhoan"):
        cat_filter = "VĨ MÔ & THỊ TRƯỜNG"
        title_suffix = "Kinh Tế Vĩ Mô & TTCK"

    async def _work() -> str:
        items = await asyncio.to_thread(_load_or_refresh_news, cat_filter, 6)
        return macro_news_card(items, title_suffix=title_suffix)

    try:
        kb = _build_news_keyboard(chat_id, current_cat=cat_filter)
        await run_with_notice(message, _work, reply_markup=kb)
    except Exception as exc:
        log.exception("Lenh /tintuc that bai")
        await message.answer(error_card(str(exc)))


@router.callback_query(F.data == "news:toggle")
async def cb_news_toggle(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    chat_id = callback.message.chat.id
    current = is_news_subscribed(chat_id)
    new_state = not current
    set_news_subscriber(chat_id, new_state)

    status_text = "BẬT" if new_state else "TẮT"
    await callback.answer(f"Đã {status_text} nhận tin tự động mỗi 1 giờ!", show_alert=False)

    kb = _build_news_keyboard(chat_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("news:cat:"))
async def cb_news_cat(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    cat_code = callback.data.split(":", 2)[2]  # type: ignore[union-attr]
    cat_filter = None if cat_code == "ALL" else cat_code
    title_suffix = "Mới Nhất"
    if cat_filter == "CHÍNH SÁCH - PHÁP LUẬT":
        title_suffix = "Chính Sách & Nghị Định"
    elif cat_filter == "VĨ MÔ & THỊ TRƯỜNG":
        title_suffix = "Vĩ Mô & TTCK"

    await callback.answer("Đang tải dữ liệu...", show_alert=False)
    items = await asyncio.to_thread(_load_or_refresh_news, cat_filter, 6)
    html_text = macro_news_card(items, title_suffix=title_suffix)

    kb = _build_news_keyboard(callback.message.chat.id, current_cat=cat_filter)
    try:
        await callback.message.edit_text(html_text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data == "news:refresh")
async def cb_news_refresh(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer("Đang làm mới từ RSS...", show_alert=False)

    def _refresh() -> list[dict]:
        raw_items = fetch_all_macro_news()
        dict_items = [it.to_dict() for it in raw_items]
        save_macro_news_items(dict_items)
        return get_recent_macro_news(limit=6)

    items = await asyncio.to_thread(_refresh)
    html_text = macro_news_card(items, title_suffix="Cập Nhật Tức Thì")
    kb = _build_news_keyboard(callback.message.chat.id)
    try:
        await callback.message.edit_text(html_text, reply_markup=kb)
    except Exception as exc:
        log.debug("Khong can sua tin nhan: %s", exc)
