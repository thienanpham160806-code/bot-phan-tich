"""Dinh dang tin nhan Telegram va tien ich trinh bay dung chung.

Quy tac bat buoc cho moi tin nhan (muc 11 cua ke hoach refactor):
  - parse_mode=HTML, escape() moi noi dung do NGUOI DUNG nhap (ten ma...).
  - The khuyen nghi co bo cuc CO DINH: dong 1 ma+khuyen nghi, khoi 2 vung
    gia, khoi 3 diem ba he, khoi 4 ba ly do.
  - Tin nhan nao co tin hieu deu kem dong mien tru trach nhiem (DISCLAIMER).
  - Lenh chay qua 2 giay: gui truoc "Dang xu ly..." roi sua lai khi xong
    (xem run_with_notice()).
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from html import escape

from aiogram.types import Message

DISCLAIMER = "<i>Sản phẩm học thuật. Không phải khuyến nghị đầu tư.</i>"
PROCESSING_NOTICE = "Đang xử lý..."
PROCESSING_THRESHOLD_SECONDS = 2.0


def money(value: float | None) -> str:
    return "không có dữ liệu" if value is None else f"{value:,.0f}"


def money_billion(value: float | None) -> str:
    """Hien so tien lon (VND) dang 'X,XXX tỷ đồng' - de doc hon so nguyen day du."""
    return "không có dữ liệu" if value is None else f"{value / 1e9:,.0f} tỷ đồng"


def price(value: float | None) -> str:
    """Gia co phieu (thang nghin dong/CP, vd 65.18) - can 2 chu so thap phan,
    khac voi money() (lam tron so nguyen, dung cho khoi luong/so CP...)."""
    return "không có dữ liệu" if value is None else f"{value:,.2f}"


def percent(value: float | None) -> str:
    return "không có dữ liệu" if value is None else f"{value:+.2%}"


# --------------------------------------------------------------------- /market
def market_card(symbol: str, close: float, change_pct: float, as_of) -> str:
    """The trang thai thi truong don gian, dua tren chi so tham chieu (VNINDEX)."""
    huong = "tăng" if change_pct >= 0 else "giảm"
    return "\n".join(
        [
            f"<b>{escape(symbol)}</b> — {as_of:%d/%m/%Y}",
            "",
            f"Điểm: <b>{price(close)}</b> ({huong} {percent(change_pct)})",
            "",
            DISCLAIMER,
        ]
    )


# ------------------------------------------------------------------ /khuyennghi
_ACTION_META = {
    "MUA": {
        "icon": "🟢",
        "title": "MUA MỚI",
        "desc": "Tín hiệu tăng giá được cả 3 hệ chỉ báo đồng thuận xác nhận.",
        "allocation": "Giải ngân 30% – 50% tiền mặt (chia làm 2 lần giải ngân, không all-in)",
    },
    "TÍCH LUỸ": {
        "icon": "🟡",
        "title": "TÍCH LUỸ / MUA THĂM DÒ",
        "desc": "Cổ phiếu đang nén nền giá hoặc hồi phục tích luỹ trong vùng an toàn.",
        "allocation": "Giải ngân 15% – 25% tiền mặt (mua gom từng phần khi giá đỏ quanh hỗ trợ)",
    },
    "THEO DÕI": {
        "icon": "⚪",
        "title": "THEO DÕI",
        "desc": "Chưa có tín hiệu vào lệnh an toàn, cơ hội và rủi ro đang ở mức cân bằng.",
        "allocation": "0% (Ưu tiên giữ tiền mặt, kiên nhẫn chờ tín hiệu bứt phá rõ ràng)",
    },
    "GIẢM TỶ TRỌNG": {
        "icon": "🟠",
        "title": "GIẢM TỶ TRỌNG",
        "desc": "Động lượng suy yếu hoặc chạm cản kỹ thuật. Rủi ro điều chỉnh ngắn hạn gia tăng.",
        "allocation": "Hạ margin, chốt lời 30% – 50% vị thế hiện tại để bảo toàn thành quả",
    },
    "BÁN": {
        "icon": "🔴",
        "title": "BÁN / THOÁT VỊ THẾ",
        "desc": "Xu hướng giảm đã xác nhận hoặc giá vi phạm ngưỡng kỹ thuật.",
        "allocation": "Bán toàn bộ vị thế hoặc cắt lỗ dứt khoát để bảo vệ vốn tối đa",
    },
}

_ACTION_EMOJI = {
    "MUA": "🟢",
    "TÍCH LUỸ": "🟡",
    "THEO DÕI": "⚪",
    "GIẢM TỶ TRỌNG": "🟠",
    "BÁN": "🔴",
}


def recommendation_card(rec) -> str:
    """The khuyen nghi chi tiet, de hieu va truc quan danh cho nha dau tu F0."""
    meta = _ACTION_META.get(
        rec.action,
        {
            "icon": "📌",
            "title": rec.action,
            "desc": "Tín hiệu kỹ thuật hiện tại của cổ phiếu.",
            "allocation": "Tuân thủ kỷ luật quản trị rủi ro danh mục.",
        },
    )

    lines = [
        f"{meta['icon']} <b>{escape(rec.symbol)}</b> — <b>KHUYẾN NGHỊ: {meta['title']}</b>",
        f"<i>{meta['desc']}</i>",
        f"💡 <b>Tỷ trọng gợi ý:</b> {meta['allocation']}",
    ]

    if rec.vetoed_by_kumo:
        lines.append(
            "⚠️ <b>LƯU Ý ĐẶC BIỆT:</b> Điểm động lượng kỹ thuật đủ MUA, nhưng hệ thống đã "
            "<b>PHỦ QUYẾT (Kumo Veto)</b> và hạ xuống <b>TÍCH LUỸ</b> do giá nằm dưới mây Kumo. "
            "Rủi ro kẹp hàng trong xu hướng giảm trung hạn rất lớn!"
        )
    if rec.confidence != "cao":
        do_tin_cay = "trung bình" if rec.confidence == "trung_binh" else "thấp"
        lines.append(
            f"⚠️ <i>Độ tin cậy: {do_tin_cay} (khối lượng thấp, thiếu xác nhận dòng tiền)</i>"
        )

    lines.extend(
        [
            "",
            "🎯 <b>KẾ HOẠCH GIAO DỊCH (TRADING PLAN)</b>",
            f"• <b>Giá hiện tại:</b> <b>{price(rec.close)}</b>",
            f"• <b>Vùng mua an toàn:</b> {price(rec.entry_low)} – {price(rec.entry_high)} "
            "<i>(Khuyến nghị: Không mua đuổi khi giá vượt vùng này)</i>",
        ]
    )

    if rec.close and rec.stop_loss:
        sl_pct = (rec.stop_loss / rec.close - 1) * 100
        sl_text = (
            f"• <b>Cắt lỗ (Stop Loss):</b> <b>{price(rec.stop_loss)}</b> "
            f"➔ <i>Rủi ro: {sl_pct:+.1f}% (Nếu thủng mức này, bán dứt khoát bảo toàn vốn)</i>"
        )
    else:
        sl_text = f"• <b>Cắt lỗ:</b> <b>{price(rec.stop_loss)}</b>"
    lines.append(sl_text)

    if rec.close and rec.target:
        tp_pct = (rec.target / rec.close - 1) * 100
        res_text = (
            f" [Kháng cự Kumo: {price(rec.target_resistance)}]"
            if rec.target_resistance is not None
            else ""
        )
        tp_text = (
            f"• <b>Mục tiêu (Take Profit):</b> <b>{price(rec.target)}</b> "
            f"➔ <i>Kỳ vọng lợi nhuận: {tp_pct:+.1f}%{res_text}</i>"
        )
    else:
        tp_text = f"• <b>Mục tiêu:</b> <b>{price(rec.target)}</b>"
    lines.append(tp_text)

    if rec.risk_reward is not None:
        rr = rec.risk_reward
        if rr >= 2.0:
            rr_eval = "Rất hấp dẫn (kỳ vọng lãi gấp đôi rủi ro)"
        elif rr >= 1.5:
            rr_eval = "Tốt, đạt chuẩn quản trị rủi ro"
        else:
            rr_eval = "Lợi nhuận chưa vượt trội rủi ro, cần cân nhắc kỹ"
        lines.append(
            f"• <b>Tỷ lệ Lợi nhuận / Rủi ro (R:R):</b> <b>{rr:.1f} : 1</b> — <i>{rr_eval}</i>"
        )
    else:
        lines.append("• <b>Tỷ lệ Lợi nhuận / Rủi ro:</b> không có dữ liệu")

    if rec.total_score >= 60:
        mood = "Tích cực mạnh (Xu hướng tăng đồng thuận)"
    elif rec.total_score >= 20:
        mood = "Tích cực (Xu hướng tăng đang hình thành)"
    elif rec.total_score >= -20:
        mood = "Trung tính (Giằng co, chưa rõ xu hướng)"
    elif rec.total_score >= -60:
        mood = "Tiêu cực (Áp lực bán chiếm ưu thế)"
    else:
        mood = "Tiêu cực mạnh (Xu hướng giảm chiếm trọn thị trường)"

    lines.extend(
        [
            "",
            f"📊 <b>PHÂN TÍCH 3 HỆ CHỈ BÁO (Điểm tổng: {rec.total_score:+.0f} / 100)</b>",
            f"<i>Trạng thái kỹ thuật: {mood}</i>",
        ]
    )

    # Indicator 1: MACD
    macd_score = rec.component_scores.get("macd", 0.0)
    lines.append(f"1️⃣ <b>MACD ({macd_score:+.0f} đ) — Động lượng ngắn hạn:</b>")
    if rec.reasons and len(rec.reasons) > 0:
        lines.append(f"   • {escape(rec.reasons[0])}")

    # Indicator 2: RSI
    rsi_score = rec.component_scores.get("rsi", 0.0)
    rsi_zone = rec.rsi_state.get("zone")
    rsi_meaning = ""
    if rsi_zone == "qua_mua":
        rsi_meaning = (
            " ➔ <i>Lực mua quá đà (quá mua), cẩn trọng rung lắc, không mua đuổi!</i>"
        )
    elif rsi_zone == "qua_ban":
        rsi_meaning = (
            " ➔ <i>Áp lực bán tháo cực đại (quá bán), có thể có nhịp hồi kỹ thuật.</i>"
        )
    elif rsi_zone == "trung_tinh":
        rsi_meaning = " ➔ <i>Vùng cân bằng an toàn, cung cầu ổn định.</i>"

    lines.append(f"2️⃣ <b>RSI ({rsi_score:+.0f} đ) — Áp lực Mua/Bán:</b>")
    if rec.reasons and len(rec.reasons) > 1:
        lines.append(f"   • {escape(rec.reasons[1])}{rsi_meaning}")

    # Indicator 3: Ichimoku
    ichi_score = rec.component_scores.get("ichimoku", 0.0)
    pos = rec.ichimoku_state.get("price_vs_kumo")
    if pos == "tren_may":
        ichi_meaning = (
            " ➔ <i>Cổ phiếu duy trì Uptrend an toàn, mây Kumo là bệ đỡ hỗ trợ phía dưới.</i>"
        )
    elif pos == "trong_may":
        ichi_meaning = " ➔ <i>Cổ phiếu đi ngang giằng co (Sideway), biến động khó lường.</i>"
    elif pos == "duoi_may":
        ichi_meaning = (
            " ➔ <i>Cổ phiếu trong Downtrend rủi ro cao, mây Kumo là rào cản kháng cự phía trên.</i>"
        )
    else:
        ichi_meaning = ""

    lines.append(f"3️⃣ <b>Ichimoku ({ichi_score:+.0f} đ) — Xu hướng trung hạn & Hỗ trợ/Kháng cự:</b>")
    if rec.reasons and len(rec.reasons) > 2:
        lines.append(f"   • {escape(rec.reasons[2])}{ichi_meaning}")

    # F0 Golden rules
    lines.extend(
        [
            "",
            "💡 <b>LỜI KHUYÊN CHO NHÀ ĐẦU TƯ F0:</b>",
            "• <b>Kỷ luật cắt lỗ:</b> Luôn tuân thủ mức cắt lỗ, không gồng lỗ khi gãy hỗ trợ.",
            "• <b>Không mua đuổi:</b> Nếu giá đã vượt vùng an toàn, hãy kiên nhẫn chờ nhịp chỉnh.",
            "• <b>Chia nhỏ lệnh:</b> Mua 2-3 đợt (thăm dò trước, gia tăng khi đúng xu hướng).",
            "",
            DISCLAIMER,
        ]
    )
    return "\n".join(lines)


# --------------------------------------------------------------------- /tracuu
def _metric_line(label: str, metric) -> str:
    if metric.value is None:
        return f"{label}: không có dữ liệu"
    text = f"{label}: {metric.value:.2f}"
    if metric.industry_median is not None:
        text += f" (trung vị ngành: {metric.industry_median:.2f})"
    return text


_DESCRIPTION_MAX_CHARS = 400


def _format_description(raw: str) -> str:
    """Mo ta hoat dong tu vnstock thuong co nhieu gach dau dong ngan cach
    boi ky tu xuong dong that (\\n) - giu NGUYEN xuong dong do (Telegram
    HTML van hien dung newline that, khac voi HTML trinh duyet), chi cat bot
    khi qua dai thay vi don het thanh mot dong lien tuc.
    """
    raw_lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]

    kept: list[str] = []
    used = 0
    for ln in raw_lines:
        if used + len(ln) > _DESCRIPTION_MAX_CHARS:
            remaining = _DESCRIPTION_MAX_CHARS - used
            if remaining > 20:  # con du cho de cat co nghia, khong thi bo han dong nay
                kept.append(ln[:remaining].rstrip() + "…")
            else:
                kept.append("…")
            break
        kept.append(ln)
        used += len(ln)

    return f"<i>{escape(chr(10).join(kept))}</i>"


def lookup_card(profile) -> str:
    lines = [
        f"<b>{escape(profile.symbol)}</b> — "
        f"{escape(profile.full_name or 'không có dữ liệu')}",
        f"Sàn: {escape(profile.exchange or 'không có dữ liệu')}  |  "
        f"Ngành: {escape(profile.industry or 'không có dữ liệu')}",
        f"Ngày niêm yết: {escape(profile.listed_date or 'không có dữ liệu')}"
        f"  |  Vốn điều lệ: {money_billion(profile.charter_capital)}",
        f"Số cổ phiếu lưu hành: {money(profile.shares_outstanding)}",
    ]

    if profile.description:
        lines.append(_format_description(profile.description))

    lines.extend(
        [
            "",
            "<b>Chỉ số chính</b>",
            f"Giá: {price(profile.price)}"
            + ("" if profile.change_pct is None else f" ({percent(profile.change_pct)})"),
            f"Khối lượng: {money(profile.volume)}",
            f"Vốn hoá: {money_billion(profile.market_cap)}",
            _metric_line("P/E", profile.pe),
            _metric_line("P/B", profile.pb),
            _metric_line("EPS", profile.eps),
            _metric_line("ROE", profile.roe),
            _metric_line("ROA", profile.roa),
            _metric_line("Biên lợi nhuận ròng", profile.net_margin),
            _metric_line("Nợ/Vốn chủ sở hữu", profile.debt_to_equity),
            _metric_line("Tỷ suất cổ tức", profile.dividend_yield),
            "",
            "<b>Cập nhật gần đây</b>",
            f"Báo cáo tài chính gần nhất: "
            f"{escape(profile.latest_report_period or 'không có dữ liệu')}",
        ]
    )

    if profile.news:
        lines.append("<b>Công bố thông tin / tin tức gần đây</b>")
        lines.extend(f"  • {escape(item)}" for item in profile.news)
    elif profile.recent_events:
        lines.extend(f"  - {escape(e)}" for e in profile.recent_events)
    else:
        lines.append("  Chưa có dữ liệu sự kiện doanh nghiệp / tin tức.")

    if profile.data_notes:
        lines.append("")
        lines.append("<i>Lưu ý dữ liệu còn thiếu:</i>")
        lines.extend(f"  - {escape(note)}" for note in profile.data_notes)

    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ----------------------------------------------------------------------- /loc
def screener_results_card(results, note: str | None = None, limit: int = 15) -> str:
    if not results:
        lines = [
            "🔍 <b>Không tìm thấy mã nào khớp điều kiện lọc hiện tại.</b>",
            "",
            "💡 <b>Lý do thường gặp:</b>",
            "• Thị trường chung đang đi ngang/điều chỉnh, ít cổ phiếu bùng nổ đồng thời.",
            "• Tiêu chí lọc quá khắt khe (ví dụ: vừa yêu cầu MUA vừa đòi hỏi RSI Quá bán).",
            "",
            "👉 <b>Gợi ý cho bạn:</b>",
            "• Thử bộ lọc 📦 <b>Tích luỹ</b> để tìm các cổ phiếu đang nén nền giá chờ tăng.",
            "• Xem tín hiệu tổng quát toàn thị trường bằng lệnh <code>/tinhieu</code>.",
            "• Thử lệnh lọc: <code>/loc san=HOSE kn=MUA</code> hoặc <code>/loc may=tren</code>",
        ]
        if note:
            lines.append("")
            lines.append(f"<i>{escape(note)}</i>")
        lines.append("")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    lines = [f"🔍 <b>Kết quả lọc cổ phiếu</b> ({len(results)} mã phù hợp)", ""]
    for r in results[:limit]:
        emoji = _ACTION_EMOJI.get(r.action, "📌")
        lines.append(
            f"{emoji} <b>{escape(r.symbol)}</b> — <b>{escape(r.action)}</b>  "
            f"| Điểm: <b>{r.total_score:+.0f}</b>  | Giá: <b>{price(r.close)}</b>"
        )
    if len(results) > limit:
        lines.append(f"<i>... và {len(results) - limit} mã khác</i>")
    if note:
        lines.append("")
        lines.append(f"<i>{escape(note)}</i>")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ------------------------------------------------------------------- /tinhieu
def signals_card(report, limit: int = 15) -> str:
    """The /tinhieu: tin hieu MUA/TICH LUY va BAN/GIAM TY TRONG cua phien gan
    nhat, kem ro phien nao (as_of) de nguoi dung biet du lieu cu hay moi."""
    if report.as_of is None:
        header = "<b>Chưa có dữ liệu tín hiệu.</b>"
        return header if not report.note else f"{header}\n\n<i>{escape(report.note)}</i>"

    lines = [f"📊 <b>Tín hiệu kỹ thuật phiên {report.as_of:%d/%m/%Y %H:%M}</b>", ""]

    lines.append(f"<b>📈 TÍN HIỆU TÍCH CỰC (MUA / TÍCH LUỸ)</b> ({len(report.buy)} mã)")
    if not report.buy:
        lines.append("  <i>Không có mã nào thoả mãn</i>")
    for r in report.buy[:limit]:
        emoji = _ACTION_EMOJI.get(r.action, "🟢")
        lines.append(
            f"  {emoji} <b>{escape(r.symbol)}</b> — {escape(r.action)}  "
            f"| Điểm: <b>{r.total_score:+.0f}</b>  | Giá: <b>{price(r.close)}</b>"
        )

    lines.append("")
    lines.append(f"<b>📉 TÍN HIỆU THẬN TRỌNG (BÁN / GIẢM TỶ TRỌNG)</b> ({len(report.sell)} mã)")
    if not report.sell:
        lines.append("  <i>Không có mã nào thoả mãn</i>")
    for r in report.sell[:limit]:
        emoji = _ACTION_EMOJI.get(r.action, "🔴")
        lines.append(
            f"  {emoji} <b>{escape(r.symbol)}</b> — {escape(r.action)}  "
            f"| Điểm: <b>{r.total_score:+.0f}</b>  | Giá: <b>{price(r.close)}</b>"
        )

    if report.note:
        lines.append("")
        lines.append(f"<i>{escape(report.note)}</i>")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ------------------------------------------------------------------- /danhsach
def watchlist_card(symbols: list[str], recommendations: dict) -> str:
    if not symbols:
        return "Danh sách theo dõi đang trống. Thêm bằng <code>/theodoi FPT</code>."

    lines = [f"<b>Đang theo dõi {len(symbols)} mã</b>", ""]
    for symbol in symbols:
        rec = recommendations.get(symbol)
        if rec is None:
            lines.append(f"<b>{escape(symbol)}</b>: không có dữ liệu")
        else:
            lines.append(
                f"<b>{escape(symbol)}</b>: {escape(rec.action)} "
                f"(điểm {rec.total_score:+.0f}, giá {price(rec.close)})"
            )
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def alerts_toggle_card(enabled: bool) -> str:
    trang_thai = "BẬT" if enabled else "TẮT"
    return f"Đã {trang_thai} cảnh báo tự động cuối phiên cho các mã bạn theo dõi."


def error_card(message: str) -> str:
    return f"Không xử lý được yêu cầu.\n\n<i>{escape(message)}</i>"


# ------------------------------------------------------------- xu ly lau > 2s
async def run_with_notice(
    message: Message,
    work: Callable[[], Awaitable[str]],
    threshold: float = PROCESSING_THRESHOLD_SECONDS,
) -> None:
    """Chay `work()` (coroutine tra ve chuoi HTML de gui cho nguoi dung).

    Neu xong truoc `threshold` giay thi gui thang ket qua. Neu lau hon, gui
    truoc PROCESSING_NOTICE roi SUA lai chinh tin nhan do bang ket qua khi
    xong - dung cho cac lenh co the mat vai giay (quet, tai BCTC...).
    """
    task = asyncio.ensure_future(work())
    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=threshold)
    except asyncio.TimeoutError:
        notice = await message.answer(PROCESSING_NOTICE)
        result = await task
        await notice.edit_text(result)
        return
    await message.answer(result)
