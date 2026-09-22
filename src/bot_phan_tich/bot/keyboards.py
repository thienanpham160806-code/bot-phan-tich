"""Ban phim nut bam - de khach hang khong phai nho cu phap lenh."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/loc"), KeyboardButton(text="/tinhieu")],
            [KeyboardButton(text="/market"), KeyboardButton(text="/watchlist")],
            [KeyboardButton(text="/canhbao"), KeyboardButton(text="/help")],
        ],
        resize_keyboard=True,
    )


def symbol_actions(symbol: str) -> InlineKeyboardMarkup:
    """Nut bam nhanh cho mot ma: bieu do, khuyen nghi, BCTC, theo doi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Biểu đồ", callback_data=f"chart:{symbol}"),
                InlineKeyboardButton(text="Khuyến nghị", callback_data=f"rec:{symbol}"),
            ],
            [
                InlineKeyboardButton(text="BCTC", callback_data=f"fin:{symbol}"),
                InlineKeyboardButton(text="Theo dõi", callback_data=f"sub:{symbol}"),
            ],
        ]
    )


def screener_menu() -> InlineKeyboardMarkup:
    """Ba bo loc dung san cho lenh /loc."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Đột phá", callback_data="screen:breakout")],
            [InlineKeyboardButton(text="📦 Tích luỹ", callback_data="screen:accumulate")],
            [InlineKeyboardButton(text="⚠️ Cảnh báo", callback_data="screen:warning")],
        ]
    )
