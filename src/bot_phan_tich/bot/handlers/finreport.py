"""Lenh /bctc (/fin): binh luan tinh hinh tai chinh tu text mining BCTC.

Nguoi dung co the gui kem file PDF BCTC ngay trong lenh; neu khong, handler
tim file da co san trong data/reports/<MA>/ (xem analysis/fintext.py). Neu
khong co PDF nao ca, van tra ve nhan xet dua tren du lieu co cau truc
(trend_analysis) - chi thieu phan y kien kiem toan va tu khoa rui ro.
"""
from __future__ import annotations

from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...analysis.fintext import (
    audit_opinion,
    extract_text,
    generate_commentary,
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


async def _save_uploaded_pdf(message: Message, bot: Bot, symbol: str) -> Path | None:
    doc = message.document
    if not doc or not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        return None
    try:
        dest = _REPORTS_DIR / symbol / doc.file_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, destination=dest)
        return dest
    except Exception as exc:
        log.warning("Khong tai duoc PDF nguoi dung gui cho %s: %s", symbol, exc)
        return None


@router.message(Command("bctc", "fin"))
async def cmd_finreport(message: Message, bot: Bot) -> None:
    symbol = parse_symbol(message)
    if not symbol:
        await message.answer("Cú pháp: <code>/bctc FPT</code> (có thể gửi kèm file PDF BCTC).")
        return

    pdf_path = await _save_uploaded_pdf(message, bot, symbol) or _find_local_pdf(symbol)

    async def work() -> str:
        try:
            audit, hits = {"opinion": None, "evidence": None}, []
            if pdf_path is not None:
                text = extract_text(pdf_path)
                audit = audit_opinion(text)
                hits = risk_keywords(text)

            financials = get_router().financials(symbol, period="year")
            trend = trend_analysis(financials)

            commentary = generate_commentary(symbol, audit, hits, trend)
            if pdf_path is None:
                commentary += _NO_PDF_NOTE
            return commentary
        except Exception as exc:
            log.exception("Lenh /bctc that bai cho %s", symbol)
            return error_card(str(exc))

    await run_with_notice(message, work)


@router.callback_query(lambda c: bool(c.data) and c.data.startswith("fin:"))
async def on_fin_callback(callback: CallbackQuery) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer()
        return
    symbol = callback.data.split(":", 1)[1]
    await callback.answer("Đang phân tích...")

    pdf_path = _find_local_pdf(symbol)
    try:
        audit, hits = {"opinion": None, "evidence": None}, []
        if pdf_path is not None:
            text = extract_text(pdf_path)
            audit = audit_opinion(text)
            hits = risk_keywords(text)
        financials = get_router().financials(symbol, period="year")
        trend = trend_analysis(financials)
        commentary = generate_commentary(symbol, audit, hits, trend)
        if pdf_path is None:
            commentary += _NO_PDF_NOTE
        await callback.message.answer(commentary)
    except Exception as exc:
        log.exception("callback bctc that bai cho %s", symbol)
        await callback.message.answer(error_card(str(exc)))
