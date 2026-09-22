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

HELP_TEXT = """<b>🤖 BOT PHÂN TÍCH KỸ THUẬT CHỨNG KHOÁN VIỆT NAM</b>
<i>Chiến lược: Hợp lưu ba hệ chỉ báo MACD, RSI thích ứng & Ichimoku Kinko Hyo.</i>

━━━━━━━━━━━━━━━━━━━━━
🎯 <b>1. NHU CẦU: PHÂN TÍCH 1 CỔ PHIẾU CỤ THỂ</b>
<i>(Gõ lệnh kèm mã cổ phiếu bạn đang quan tâm hoặc nắm giữ)</i>

• <code>/kn &lt;mã&gt;</code> — <b>Khuyến nghị & Kế hoạch giao dịch</b>
  ➔ Vùng mua an toàn, cắt lỗ (% rủi ro), mục tiêu (% kỳ vọng), tỷ lệ R:R và 3 chỉ báo.
  <i>Ví dụ: <code>/kn FPT</code> hoặc <code>/kn MBB</code></i>

• <code>/chart &lt;mã&gt;</code> — <b>Biểu đồ kỹ thuật nến Nhật</b>
  ➔ Biểu đồ nến trực quan tích hợp mây Ichimoku, MACD và RSI.
  <i>Ví dụ: <code>/chart SSI</code></i>

• <code>/info &lt;mã&gt;</code> — <b>Hồ sơ doanh nghiệp & Định giá</b>
  ➔ Chỉ số P/E, P/B, ROE, ngành nghề, vốn hoá và tin tức công bố thông tin.
  <i>Ví dụ: <code>/info VNM</code></i>

• <code>/fin &lt;mã&gt;</code> — <b>Báo cáo tài chính & Sức khỏe nợ vay</b>
  ➔ Bóc tách cơ cấu nợ, dòng tiền và cảnh báo rủi ro thuyết minh (có thể đính kèm PDF).
  <i>Ví dụ: <code>/fin HPG</code></i>

━━━━━━━━━━━━━━━━━━━━━
🔍 <b>2. NHU CẦU: TÌM CƠ HỘI ĐẦU TƯ TOÀN SÀN</b>
<i>(Quét toàn bộ thị trường, không cần nhập mã cụ thể)</i>

• <code>/loc</code> — <b>Bộ lọc cổ phiếu thông minh</b>
  ➔ Bấm 1 trong 3 nút chiến lược dựng sẵn:
     🚀 <b>Đột phá:</b> Vượt mây Kumo + MACD cắt lên + Von nổ
     📦 <b>Tích luỹ:</b> Nén nền chặt + RSI an toàn + Von cạn kiệt
     ⚠️ <b>Cảnh báo:</b> Thủng mây hoặc Phân kỳ âm
  ➔ Hoặc gõ điều kiện tuỳ biến:
     <code>/loc san=HOSE kn=MUA</code> (Lọc mã MUA trên sàn HOSE)
     <code>/loc may=tren kl=1.2</code> (Mã nằm trên mây, khối lượng tăng)

• <code>/tinhieu</code> — <b>Tín hiệu MUA / BÁN trong ngày</b>
  ➔ Danh sách cổ phiếu xuất hiện tín hiệu MUA/TÍCH LUỸ hoặc BÁN ở phiên gần nhất.

• <code>/market</code> — <b>Xu hướng thị trường chung (VN-Index)</b>
  ➔ Đánh giá sức mạnh thị trường để quyết định giải ngân hay giữ tiền.

• <code>/tintuc</code> — <b>Bản tin vĩ mô, nghị định & luật thị trường</b>
  ➔ Tổng hợp tin tức vĩ mô, văn bản pháp quy, nghị định, nghị quyết mới nhất.
  ➔ Bật nhận tin tự động mỗi 1 giờ: <code>/tintuc on</code> (hoặc <code>/tintuc off</code>).

━━━━━━━━━━━━━━━━━━━━━
⭐ <b>3. NHU CẦU: QUẢN LÝ DANH MỤC & CẢNH BÁO</b>
<i>(Lưu danh mục cá nhân để bot theo dõi hộ bạn mỗi ngày)</i>

• <code>/sub &lt;mã&gt;</code> — Thêm mã vào danh mục theo dõi (VD: <code>/sub FPT</code>)
• <code>/watchlist</code> — Xem lại danh mục theo dõi kèm khuyến nghị hôm nay
• <code>/unsub &lt;mã&gt;</code> — Bỏ theo dõi một mã (VD: <code>/unsub FPT</code>)
• <code>/canhbao</code> — Bật/Tắt thông báo tự động cuối phiên (15:05 mỗi ngày)

━━━━━━━━━━━━━━━━━━━━━
💡 <i>Mẹo: Bạn có thể chạm nhanh vào các lệnh có khung màu xám (code) ở trên để copy vào ô chat!</i>
<i>(Hỗ trợ cả lệnh cũ: /khuyennghi, /bieudo, /tracuu, /bctc, /theodoi, /danhsach...)</i>

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
        change_pts = (float(last["close"]) - float(prev["close"])) if prev["close"] else 0.0
        change_pct = (change_pts / float(prev["close"])) if prev["close"] else 0.0
        await message.answer(
            market_card(
                benchmark,
                float(last["close"]),
                change_pct,
                last["time"].date(),
                change_pts=change_pts,
                high=float(last.get("high", 0)),
                low=float(last.get("low", 0)),
                volume=float(last.get("volume", 0)),
            )
        )
    except Exception as exc:
        log.exception("Lenh /market that bai")
        await message.answer(error_card(str(exc)))
