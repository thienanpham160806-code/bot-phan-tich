"""Lenh /khuyennghi (/rec, /kn) va /bieudo (/chart)."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ...analysis.scoring import recommend as compute_recommendation
from ...data.router import get_router
from ...logging_conf import get_logger
from ..charts import candlestick_png
from ..formatters import error_card, recommendation_card, run_with_notice
from ..keyboards import symbol_actions
from .common import parse_symbol

log = get_logger(__name__)
router = Router(name="recommend")

_LOOKBACK_DAYS = 500
_MIN_BARS = 60


def _load_frame(symbol: str, days: int = _LOOKBACK_DAYS):
    """Nap gia va kiem tra du lieu toi thieu. Nem ValueError voi thong bao
    de hieu neu ma khong ton tai hoac chua du lich su - de handler bat va
    hien thi bang error_card(), khong sap bot."""
    end = date.today()
    frame = get_router().ohlcv(symbol, end - timedelta(days=days), end)
    if frame.empty:
        raise ValueError(f"Không có dữ liệu giá cho {symbol}. Mã có thể không tồn tại.")
    if len(frame) < _MIN_BARS:
        raise ValueError(f"{symbol} chưa đủ lịch sử ({len(frame)} phiên) để tính chỉ báo.")
    return frame


@router.message(Command("khuyennghi", "rec", "kn"))
async def cmd_recommend(message: Message) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer("Cú pháp: <code>/khuyennghi FPT</code>")
        return

    async def work() -> str:
        try:
            frame = await asyncio.to_thread(_load_frame, symbol)
            rec = await asyncio.to_thread(compute_recommendation, frame, symbol)
            return recommendation_card(rec)
        except Exception as exc:
            log.exception("Lenh /khuyennghi that bai cho %s", symbol)
            return error_card(str(exc))

    await run_with_notice(message, work)


@router.message(Command("bieudo", "chart"))
async def cmd_chart(message: Message) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer("Cú pháp: <code>/bieudo FPT</code>")
        return

    try:
        frame = await asyncio.to_thread(_load_frame, symbol, days=300)
        rec = await asyncio.to_thread(compute_recommendation, frame, symbol)
        png = await asyncio.to_thread(
            candlestick_png, frame, symbol, stop_loss=rec.stop_loss, target=rec.target
        )
        await message.answer_photo(
            BufferedInputFile(png, filename=f"{symbol}.png"),
            caption=f"{symbol} — biểu đồ kỹ thuật (mây Ichimoku, MACD, RSI)",
            reply_markup=symbol_actions(symbol),
        )
    except Exception as exc:
        log.exception("Lenh /bieudo that bai cho %s", symbol)
        await message.answer(error_card(str(exc)))


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("chart:"))
async def on_chart_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return
    symbol = callback.data.split(":", 1)[1]
    await callback.answer()
    try:
        frame = await asyncio.to_thread(_load_frame, symbol, days=300)
        rec = await asyncio.to_thread(compute_recommendation, frame, symbol)
        png = await asyncio.to_thread(
            candlestick_png, frame, symbol, stop_loss=rec.stop_loss, target=rec.target
        )
        await callback.message.answer_photo(
            BufferedInputFile(png, filename=f"{symbol}.png"),
            caption=f"{symbol} — biểu đồ kỹ thuật",
        )
    except Exception as exc:
        log.exception("callback bieu do that bai cho %s", symbol)
        await callback.message.answer(error_card(str(exc)))


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("rec:"))
async def on_rec_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return
    symbol = callback.data.split(":", 1)[1]
    await callback.answer()
    try:
        frame = await asyncio.to_thread(_load_frame, symbol)
        rec = await asyncio.to_thread(compute_recommendation, frame, symbol)
        await callback.message.answer(recommendation_card(rec))
    except Exception as exc:
        log.exception("callback khuyen nghi that bai cho %s", symbol)
        await callback.message.answer(error_card(str(exc)))
