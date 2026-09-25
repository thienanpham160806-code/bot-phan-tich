"""Kiem thu /fin: doc ma tu chu thich file, PDF gui kem/reply, PDF scan, BCTC
ngan hang va loi dao thu tu nam cua vnstock."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from aiogram.types import Chat, Document, Message  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from bot_phan_tich.analysis.fintext import (  # noqa: E402
    extract_text,
    is_scanned_text,
    trend_analysis,
)
from bot_phan_tich.bot.handlers import finreport  # noqa: E402
from bot_phan_tich.bot.handlers.common import parse_symbol  # noqa: E402
from bot_phan_tich.data.vietcap import align_statement_years  # noqa: E402

CHAT = Chat(id=1, type="private")


def _doc(name="BCTC.pdf", size=1_000) -> Document:
    return Document(file_id="f", file_unique_id="u", file_name=name, file_size=size)


def _msg(text=None, caption=None, document=None, reply_to=None) -> Message:
    return Message(
        message_id=1, date=datetime.now(timezone.utc), chat=CHAT, text=text,
        caption=caption, document=document, reply_to_message=reply_to,
    )


def _text_pdf(path, lines: list[str], pages: int = 1) -> None:
    matplotlib.rcParams["pdf.fonttype"] = 42
    with PdfPages(path) as pdf:
        for _ in range(pages):
            fig = plt.figure(figsize=(8.27, 11.69))
            for i, line in enumerate(lines):
                fig.text(0.05, 0.95 - i * 0.03, line, fontsize=9)
            pdf.savefig(fig)
            plt.close(fig)


# ------------------------------------------------------------- nhan PDF
def test_symbol_is_read_from_file_caption():
    """Gui file kem chu thich "/fin ctg": lenh nam o caption, text rong."""
    assert parse_symbol(_msg(caption="/fin ctg", document=_doc())) == "CTG"
    assert parse_symbol(_msg(text="/fin fpt")) == "FPT"


def test_pdf_found_in_message_or_in_replied_message():
    pdf = _doc()
    assert finreport._attached_pdf(_msg(caption="/fin CTG", document=pdf)) is pdf
    replied = _msg(document=pdf)
    assert finreport._attached_pdf(_msg(text="/fin CTG", reply_to=replied)) is pdf
    assert finreport._attached_pdf(_msg(text="/fin CTG", document=_doc("anh.png"))) is None


def test_pdf_over_telegram_limit_is_reported_without_download():
    class NoBot:
        async def get_file(self, *_a):
            raise AssertionError("khong duoc tai file > 20 MB")

    path, error = asyncio.run(
        finreport._save_uploaded_pdf(_doc(size=25 * 1024 * 1024), NoBot(), "CTG")
    )
    assert path is None and "20 MB" in error


# ------------------------------------------------------------- doc PDF
def test_extract_text_keeps_vietnamese(tmp_path):
    pdf = tmp_path / "bctc.pdf"
    _text_pdf(pdf, ["Ý kiến của kiểm toán viên: chấp nhận toàn phần."], pages=3)
    text = extract_text(pdf)
    assert "Ý kiến của kiểm toán viên" in text and "\r" not in text
    assert not is_scanned_text(text * 20)


def test_scanned_pdf_is_explained(tmp_path, monkeypatch):
    scan = tmp_path / "scan.pdf"
    with PdfPages(scan) as pdf:  # chi co anh, khong co lop chu
        fig = plt.figure()
        fig.figimage(np.random.default_rng(0).random((50, 50)))
        pdf.savefig(fig)
        plt.close(fig)

    class Router:
        def financials(self, *_a, **_k):
            return {k: pd.DataFrame() for k in ("income", "balance", "cashflow", "ratios")}

    monkeypatch.setattr(finreport, "get_router", lambda: Router())
    assert "bản scan" in finreport._build_commentary("CTG", scan)


def test_text_pdf_is_mined(tmp_path, monkeypatch):
    pdf = tmp_path / "bctc.pdf"
    _text_pdf(pdf, [
        "BÁO CÁO KIỂM TOÁN ĐỘC LẬP",
        "Ý kiến của kiểm toán viên",
        "Theo ý kiến của chúng tôi, báo cáo tài chính đã phản ánh trung thực và hợp lý,",
        "trên các khía cạnh trọng yếu. Ý kiến chấp nhận toàn phần.",
    ] * 5, pages=2)

    class Router:
        def financials(self, *_a, **_k):
            return {k: pd.DataFrame() for k in ("income", "balance", "cashflow", "ratios")}

    monkeypatch.setattr(finreport, "get_router", lambda: Router())
    text = finreport._build_commentary("CTG", pdf)
    assert "Đã khai thác file PDF: bctc.pdf" in text
    assert "Chưa có file PDF" not in text


# ------------------------------------------------- BCTC ngan hang, thu tu nam
def test_bank_metrics_in_trend():
    years = ["2022", "2023", "2024", "2025"]
    income = pd.DataFrame({
        "period": years, "net_profit": [17e12, 20e12, 25e12, 35e12],
        "net_interest_income": [48e12, 53e12, 62e12, 66e12],
        "provision_for_credit_losses": [24e12, 25e12, 28e12, 17e12],
    })
    balance = pd.DataFrame({
        "period": years, "total_assets": [1.8e15, 2.0e15, 2.4e15, 2.8e15],
        "capital_and_reserves": [1.1e14, 1.3e14, 1.5e14, 1.8e14],
        "loans_advances_and_finance_leases_to_customers": [1.2e15, 1.4e15, 1.7e15, 2.0e15],
        "deposits_from_customers": [1.2e15, 1.4e15, 1.6e15, 1.8e15],
    })
    trend = trend_analysis({"income": income, "balance": balance,
                            "cashflow": pd.DataFrame(), "ratios": pd.DataFrame()})
    assert trend["net_interest_income_by_year"]["2025"] == 66e12
    assert trend["net_interest_income_cagr"] > 0
    assert trend["equity_by_year"]["2022"] == 1.1e14
    assert trend["customer_deposits_by_year"]["2024"] == 1.6e15


def _hpg_like_bundle(reversed_labels: bool) -> dict:
    """Loi nhuan that HPG 2022-2025: 8.444 / 6.800 / 12.020 / 15.515 ty."""
    years = ["2022", "2023", "2024", "2025"]
    profit = [8444e9, 6800e9, 12020e9, 15515e9]
    assets = [170e12, 187e12, 224e12, 250e12]
    if reversed_labels:  # nhu vnstock 4.0.8: so lieu xep nguoc voi nhan nam
        profit, assets = profit[::-1], assets[::-1]
    return {
        "income": pd.DataFrame({"period": years, "net_profit": profit}),
        "balance": pd.DataFrame({"period": years, "total_assets": assets}),
        "cashflow": pd.DataFrame({"period": years, "operating_cash_flow": [1, 2, 3, 4]}),
        "ratios": pd.DataFrame({
            "period": years,
            "profit_after_tax_for_shareholders_of_the_parent_company": [-75.4, -19.4, 75.9, 28.6],
        }),
    }


def test_reversed_statement_years_are_fixed_and_idempotent():
    fixed = align_statement_years(_hpg_like_bundle(reversed_labels=True))
    income = fixed["income"].set_index("period")["net_profit"]
    assert income["2022"] == 8444e9 and income["2025"] == 15515e9
    assert fixed["balance"].set_index("period")["total_assets"]["2025"] == 250e12
    assert list(fixed["cashflow"]["operating_cash_flow"]) == [4, 3, 2, 1]
    # Goi lai tren du lieu da sua (vd doc tu cache): khong dao them lan nua.
    again = align_statement_years(fixed)
    assert again["income"].set_index("period")["net_profit"]["2022"] == 8444e9


def test_correct_statement_years_are_left_alone():
    bundle = _hpg_like_bundle(reversed_labels=False)
    fixed = align_statement_years(bundle)
    assert fixed["income"].set_index("period")["net_profit"]["2025"] == 15515e9


@pytest.mark.parametrize("missing", ["income", "ratios"])
def test_alignment_skips_when_evidence_missing(missing):
    bundle = _hpg_like_bundle(reversed_labels=True)
    bundle[missing] = pd.DataFrame()
    assert align_statement_years(bundle) is bundle
