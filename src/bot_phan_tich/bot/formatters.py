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
def recommendation_card(rec) -> str:
    """The khuyen nghi - bo cuc CO DINH theo dung 4 khoi yeu cau o muc 11."""
    lines = [f"<b>{escape(rec.symbol)}</b> — <b>{escape(rec.action)}</b>"]
    if rec.vetoed_by_kumo:
        lines.append("<i>(Điểm gốc đủ MUA, nhưng bị Ichimoku phủ quyết vì giá dưới mây Kumo)</i>")
    if rec.confidence != "cao":
        do_tin_cay = rec.confidence.replace("_", " ")
        lines.append(f"<i>Độ tin cậy: {escape(do_tin_cay)} (khối lượng thấp)</i>")
    lines.append("")

    lines.append(f"Giá hiện tại: <b>{price(rec.close)}</b>")
    lines.append(f"Vùng vào: {price(rec.entry_low)} – {price(rec.entry_high)}")
    lines.append(f"Cắt lỗ: <b>{price(rec.stop_loss)}</b>")
    target_line = f"Mục tiêu: <b>{price(rec.target)}</b>"
    if rec.target_resistance is not None:
        target_line += f" (kháng cự Ichimoku gần nhất: {price(rec.target_resistance)})"
    lines.append(target_line)
    rr = "không có dữ liệu" if rec.risk_reward is None else f"{rec.risk_reward:.1f}R"
    lines.append(f"Tỷ lệ lợi nhuận/rủi ro: {rr}")
    lines.append("")

    lines.append("<b>Điểm ba hệ chỉ báo</b>")
    lines.append(f"  MACD: {rec.component_scores['macd']:+.0f}")
    lines.append(f"  RSI: {rec.component_scores['rsi']:+.0f}")
    lines.append(f"  Ichimoku: {rec.component_scores['ichimoku']:+.0f}")
    lines.append(f"  <b>Điểm tổng: {rec.total_score:+.0f}</b>")
    lines.append("")

    lines.append("<b>Lý do</b>")
    for i, reason in enumerate(rec.reasons, start=1):
        lines.append(f"  {i}. {escape(reason)}")
    lines.append("")

    lines.append(DISCLAIMER)
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
        header = "<b>Không tìm thấy mã nào khớp điều kiện.</b>"
        return header if not note else f"{header}\n\n<i>{escape(note)}</i>"

    lines = [f"<b>Kết quả lọc</b> ({len(results)} mã)", ""]
    for r in results[:limit]:
        lines.append(
            f"<b>{escape(r.symbol)}</b>  {escape(r.action)}  "
            f"điểm {r.total_score:+.0f}  giá {price(r.close)}"
        )
    if len(results) > limit:
        lines.append(f"<i>... và {len(results) - limit} mã khác</i>")
    if note:
        lines.append("")
        lines.append(f"<i>{escape(note)}</i>")
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
