"""Lenh theo doi: /theodoi (/sub), /bosach (/unsub), /danhsach (/watchlist), /canhbao (/alerts)."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...alerts import watchlist as watchlist_store
from ...analysis.scoring import recommend as compute_recommendation
from ...data.router import get_router
from ...logging_conf import get_logger
from ..formatters import alerts_toggle_card, error_card, watchlist_card
from .common import parse_symbol

log = get_logger(__name__)
router = Router(name="watchlist")

_MIN_BARS = 60


@router.message(Command("theodoi", "sub"))
async def cmd_sub(message: Message) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer("Cú pháp: <code>/theodoi FPT</code>")
        return
    try:
        watchlist_store.add(message.chat.id, symbol)
        await message.answer(f"Đã thêm <b>{symbol}</b> vào danh sách theo dõi.")
    except Exception as exc:
        log.exception("Lenh /theodoi that bai cho %s", symbol)
        await message.answer(error_card(str(exc)))


@router.message(Command("bosach", "unsub"))
async def cmd_unsub(message: Message) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer("Cú pháp: <code>/bosach FPT</code>")
        return
    try:
        watchlist_store.remove(message.chat.id, symbol)
        await message.answer(f"Đã bỏ theo dõi <b>{symbol}</b>.")
    except Exception as exc:
        log.exception("Lenh /bosach that bai cho %s", symbol)
        await message.answer(error_card(str(exc)))


@router.message(Command("danhsach", "watchlist"))
async def cmd_watchlist(message: Message) -> None:
    try:
        symbols = watchlist_store.list_symbols(message.chat.id)
        recommendations = {}
        data = get_router()
        end = date.today()
        for symbol in symbols:
            try:
                frame = data.ohlcv(symbol, end - timedelta(days=400), end)
                if len(frame) >= _MIN_BARS:
                    recommendations[symbol] = compute_recommendation(frame, symbol)
            except Exception as exc:
                log.warning("danhsach: bo qua %s do loi: %s", symbol, exc)
        await message.answer(watchlist_card(symbols, recommendations))
    except Exception as exc:
        log.exception("Lenh /danhsach that bai")
        await message.answer(error_card(str(exc)))


@router.message(Command("canhbao", "alerts"))
async def cmd_toggle_alerts(message: Message) -> None:
    try:
        enabled = watchlist_store.toggle_alerts(message.chat.id)
        await message.answer(alerts_toggle_card(enabled))
    except Exception as exc:
        log.exception("Lenh /canhbao that bai")
        await message.answer(error_card(str(exc)))


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("sub:"))
async def on_sub_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return
    symbol = callback.data.split(":", 1)[1]
    try:
        watchlist_store.add(callback.message.chat.id, symbol)
        await callback.answer(f"Đã thêm {symbol} vào theo dõi")
    except Exception:
        log.exception("callback theo doi that bai cho %s", symbol)
        await callback.answer("Lỗi khi thêm vào danh sách theo dõi")
