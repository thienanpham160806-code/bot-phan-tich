"""Lenh chung: /start, /help, /market - va tien ich dung chung cho handlers khac."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ...config import get_universe_config
from ...data.router import get_router
from ...logging_conf import get_logger
from ..formatters import error_card, market_card
from ..keyboards import main_menu

log = get_logger(__name__)
router = Router(name="common")

HELP_TEXT = """<b>Bot phân tích kỹ thuật chứng khoán Việt Nam</b>

Chiến lược: hợp lưu ba hệ chỉ báo MACD, RSI, Ichimoku Kinko Hyo.

<b>Lệnh có sẵn</b>
/tracuu MA (/info) — hồ sơ + chỉ số chính + cập nhật gần đây
/khuyennghi MA (/rec, /kn) — khuyến nghị mua/bán, điểm ba hệ, giá vào/cắt lỗ/mục tiêu
/bieudo MA (/chart) — biểu đồ nến kèm mây Ichimoku, MACD, RSI
/loc (/screen) — lọc cổ phiếu, có nút bấm cho ba bộ lọc dựng sẵn
/bctc MA (/fin) — bình luận tình hình tài chính (gửi kèm PDF BCTC nếu có)
/theodoi MA (/sub) — thêm vào danh sách theo dõi
/bosach MA (/unsub) — bỏ theo dõi
/danhsach (/watchlist) — xem danh sách theo dõi kèm khuyến nghị hiện tại
/canhbao (/alerts) — bật/tắt cảnh báo tự động cuối phiên
/market — trạng thái chỉ số tham chiếu (VNINDEX)
/help (/start) — hướng dẫn này

<i>Sản phẩm học thuật. Không phải khuyến nghị đầu tư.</i>"""


def parse_symbol(message: Message) -> str | None:
    """Lay tham so dau tien sau ten lenh (ma co phieu), vien hoa. None neu thieu."""
    parts = (message.text or "").split()
    return parts[1].upper() if len(parts) > 1 else None


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("market"))
async def cmd_market(message: Message) -> None:
    try:
        data = get_router()
        benchmark = get_universe_config().get("benchmark", "VNINDEX")
        end = date.today()
        frame = await asyncio.to_thread(data.ohlcv, benchmark, end - timedelta(days=30), end)
        if frame.empty:
            await message.answer(error_card(f"Không có dữ liệu cho {benchmark}"))
            return
        last = frame.iloc[-1]
        prev = frame.iloc[-2] if len(frame) > 1 else last
        change_pct = (float(last["close"]) / float(prev["close"]) - 1) if prev["close"] else 0.0
        await message.answer(
            market_card(benchmark, float(last["close"]), change_pct, last["time"].date())
        )
    except Exception as exc:
        log.exception("Lenh /market that bai")
        await message.answer(error_card(str(exc)))
