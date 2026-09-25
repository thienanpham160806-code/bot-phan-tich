"""Lenh /bctc (/fin): binh luan tinh hinh tai chinh tu text mining BCTC.

Nguoi dung co the gui kem file PDF BCTC ngay trong lenh; neu khong, handler
tim file da co san trong data/reports/<MA>/ (xem analysis/fintext.py). Neu
khong co PDF nao ca, van tra ve nhan xet dua tren du lieu co cau truc
(trend_analysis) - chi thieu phan y kien kiem toan va tu khoa rui ro.
"""
from __future__ import annotations

import asyncio
from html import escape
from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Document, Message

from ...analysis.fintext import (
    audit_opinion,
    extract_text,
    generate_commentary,
    is_scanned_text,
    risk_keywords,
    trend_analysis,
)
from ...data.router import get_router
from ...logging_conf import get_logger
from ..formatters import error_card, run_with_notice
from .common import parse_symbol

log = get_logger(__name__)
router = Router(name="finreport")

_REPORTS_DIR = Path("data/reports")
_NO_PDF_NOTE = (
    "\n\n<i>Chưa có file PDF BCTC cho mã này — phần ý kiến kiểm toán và rủi ro "
    "thuyết minh dựa trên dữ liệu có cấu trúc. Gửi kèm PDF cùng lệnh /bctc hoặc "
    "đặt vào data/reports/&lt;MÃ&gt;/ để phân tích đầy đủ hơn.</i>"
)


def _find_local_pdf(symbol: str) -> Path | None:
    folder = _REPORTS_DIR / symbol
    if not folder.is_dir():
        return None
    pdfs = sorted(folder.glob("*.pdf"))
    return pdfs[-1] if pdfs else None


_TELEGRAM_DOWNLOAD_LIMIT = 20 * 1024 * 1024  # Bot API chi cho bot tai file <= 20 MB


def _is_pdf(doc: Document | None) -> bool:
    return bool(doc and doc.file_name and doc.file_name.lower().endswith(".pdf"))


def _attached_pdf(message: Message) -> Document | None:
    """PDF gui KEM lenh (lenh la chu thich cua file), hoac PDF trong tin nhan
    ma lenh /fin dang tra loi (reply)."""
    if _is_pdf(message.document):
        return message.document
    replied = message.reply_to_message
    if replied is not None and _is_pdf(replied.document):
        return replied.document
    return None


async def _save_uploaded_pdf(
    doc: Document, bot: Bot, symbol: str
) -> tuple[Path | None, str | None]:
    """(duong dan file da tai, loi de bao nguoi dung neu khong tai duoc)."""
    if doc.file_size and doc.file_size > _TELEGRAM_DOWNLOAD_LIMIT:
        return None, (
            f"File PDF {doc.file_size / 1024 / 1024:.1f} MB lớn hơn 20 MB — Telegram "
            "không cho bot tải file lớn hơn mức này. Hãy gửi bản nén nhỏ hơn."
        )
    try:
        # Chi lay TEN file: file_name do nguoi gui dat, co the chua "../".
        dest = _REPORTS_DIR / Path(symbol).name / Path(doc.file_name).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, destination=dest)
        return dest, None
    except Exception as exc:
        log.warning("Khong tai duoc PDF nguoi dung gui cho %s: %s", symbol, exc)
        return None, "Không tải được file PDF từ Telegram, phân tích tiếp không có PDF."


def _build_commentary(symbol: str, pdf_path: Path | None) -> str:
    """Toan bo logic nang (doc PDF, mining van ban, doc bao cao tai chinh) - chay
    trong mot thread rieng qua asyncio.to_thread() o ca hai noi goi ben duoi,
    khong duoc chan event loop cua bot."""
    audit, hits = {"opinion": None, "evidence": None}, []
    pdf_note = ""
    if pdf_path is not None:
        text = extract_text(pdf_path)
        if is_scanned_text(text):
            # BCTC kiem toan hay la ban scan co chu ky/dau - khong co lop chu.
            pdf_note = (
                "\n\n<i>File PDF gần như không có chữ (bản scan/chụp ảnh) nên không "
                "khai thác được ý kiến kiểm toán và thuyết minh. Cần bản PDF có thể "
                "bôi đen/copy được chữ — thường là bản tải từ website công ty hoặc "
                "CafeF/Vietstock.</i>"
            )
        else:
            audit = audit_opinion(text)
            hits = risk_keywords(text)
            pdf_note = f"\n\n<i>Đã khai thác file PDF: {escape(pdf_path.name)}.</i>"

    financials = get_router().financials(symbol, period="year")
    if pdf_path is None and all(frame.empty for frame in financials.values()):
        # Thuong gap nhat: vnstock goi mien phi gioi han 20 luot/phut, vua goi
        # /info (nhieu luot) xong goi /fin ngay la het luot. Noi ro thay vi in
        # sau muc "khong co du lieu".
        return (
            f"⚠️ Chưa lấy được báo cáo tài chính của <b>{escape(symbol)}</b>. Nguồn dữ "
            "liệu (Vietcap qua vnstock, gói miễn phí giới hạn 20 lượt/phút) có thể đang "
            "tạm từ chối — thử lại sau khoảng 1 phút. Nếu vẫn không có, mã này có thể "
            "chưa có BCTC năm."
        )
    trend = trend_analysis(financials)

    commentary = generate_commentary(symbol, audit, hits, trend)
    return commentary + (_NO_PDF_NOTE if pdf_path is None else pdf_note)


@router.message(Command("bctc", "fin"))
async def cmd_finreport(message: Message, bot: Bot) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer(
            "Cú pháp: <code>/fin FPT</code> (hoặc <code>/bctc FPT</code>, "
            "có thể gửi kèm file PDF BCTC)."
        )
        return

    pdf_path, upload_error = None, None
    doc = _attached_pdf(message)
    if doc is not None:
        pdf_path, upload_error = await _save_uploaded_pdf(doc, bot, symbol)
    pdf_path = pdf_path or _find_local_pdf(symbol)

    async def work() -> str:
        try:
            text = await asyncio.to_thread(_build_commentary, symbol, pdf_path)
        except Exception as exc:
            log.exception("Lenh /bctc that bai cho %s", symbol)
            return error_card(str(exc))
        return text + (f"\n\n⚠️ <i>{escape(upload_error)}</i>" if upload_error else "")

    await run_with_notice(message, work)


@router.message(lambda m: _is_pdf(m.document))
async def on_pdf_without_command(message: Message) -> None:
    """PDF gui rieng, khong kem lenh: ban cu im lang - nguoi dung tuong bot da
    doc file roi go /fin o tin nhan sau, file do bi bo qua."""
    await message.reply(
        "📄 Đã nhận file PDF. Để bot khai thác BCTC này, <b>trả lời (reply) chính "
        "file này</b> bằng lệnh <code>/fin MÃ</code> (vd <code>/fin CTG</code>), hoặc "
        "gửi lại file kèm chú thích <code>/fin MÃ</code>."
    )


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("fin:"))
async def on_fin_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return
    symbol = callback.data.split(":", 1)[1]
    await callback.answer("Đang phân tích...")

    pdf_path = _find_local_pdf(symbol)
    try:
        commentary = await asyncio.to_thread(_build_commentary, symbol, pdf_path)
        await callback.message.answer(commentary)
    except Exception as exc:
        log.exception("callback bctc that bai cho %s", symbol)
        await callback.message.answer(error_card(str(exc)))
