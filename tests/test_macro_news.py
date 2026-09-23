"""Kiem thu tinh nang tong hop tin tuc vi mo, phap luat va nghi dinh."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot_phan_tich.bot.formatters import macro_news_card
from bot_phan_tich.config import Paths
from bot_phan_tich.data import cache
from bot_phan_tich.data.cache import (
    get_news_subscribers,
    get_recent_macro_news,
    init_db,
    is_news_subscribed,
    save_macro_news_items,
    set_news_subscriber,
)
from bot_phan_tich.data.macro_news import classify_news, clean_html


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """DB SQLite rieng cho test, da tao du bang bang init_db(). Truoc day test
    ghi thang vao data/cache.sqlite3 THAT: loi "no such table:
    macro_news_items" tren may co DB cu/chua tao, va de lai tin gia trong
    bang ma /tintuc doc ra cho nguoi dung that."""
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(cache, "get_paths", lambda: paths)
    init_db()
    return paths


def test_clean_html():
    raw = (
        "<a href='https://example.com'><img src='pic.jpg'/></a>"
        "<p>Thủ tướng ban hành <b>Nghị định</b> mới.</p>"
    )
    clean = clean_html(raw)
    assert "<" not in clean
    assert ">" not in clean
    assert "Thủ tướng ban hành Nghị định mới." in clean


def test_classify_news():
    # Nghi dinh / Nghi quyet
    cat1 = classify_news("Chính phủ ban hành Nghị định 12 về thị trường chứng khoán", "")
    assert cat1 == "CHÍNH SÁCH - PHÁP LUẬT"

    cat2 = classify_news("Quốc hội thông qua Nghị quyết phát triển kinh tế", "")
    assert cat2 == "CHÍNH SÁCH - PHÁP LUẬT"

    # Vi mo & Tai chinh
    cat3 = classify_news("Ngân hàng Nhà nước hạ lãi suất tái cấp vốn", "Áp lực tỷ giá hạ nhiệt")
    assert cat3 == "CHÍNH SÁCH - PHÁP LUẬT" or cat3 == "VĨ MÔ & THỊ TRƯỜNG"

    cat4 = classify_news(
        "Thanh khoản thị trường bùng nổ, khối ngoại gom ròng", "VN-Index vượt đỉnh"
    )
    assert cat4 == "VĨ MÔ & THỊ TRƯỜNG"

    # Mac dinh
    cat5 = classify_news("Vinamilk mở rộng trang trại bò sữa tại Cần Thơ", "Sản lượng sữa tăng")
    assert cat5 == "DOANH NGHIỆP & NGÀNH"


def test_cache_news_dedup_and_subscribers(isolated_db):
    import uuid

    uid1 = f"test-{uuid.uuid4()}"
    uid2 = f"test-{uuid.uuid4()}"
    items = [
        {
            "guid": uid1,
            "title": "Chính phủ ban hành nghị định mới",
            "link": f"https://cafef.vn/{uid1}.chn",
            "category": "CHÍNH SÁCH - PHÁP LUẬT",
            "summary": "Chi tiết về nghị định mới",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source": "CafeF",
        },
        {
            "guid": uid2,
            "title": "Tỷ giá USD hạ nhiệt, thanh khoản dồi dào",
            "link": f"https://cafef.vn/{uid2}.chn",
            "category": "VĨ MÔ & THỊ TRƯỜNG",
            "summary": "Thị trường tiền tệ ổn định",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source": "VnExpress",
        },
    ]

    # Lan 1: Luu thanh cong 2 tin moi
    new_items_1 = save_macro_news_items(items)
    assert len(new_items_1) == 2

    # Lan 2: Khong chen trung do da ton tai guid
    new_items_2 = save_macro_news_items(items)
    assert len(new_items_2) == 0

    recent = get_recent_macro_news(limit=5)
    assert len(recent) >= 2

    # Kiem tra chuc nang subscriber
    test_chat_id = 999888777
    set_news_subscriber(test_chat_id, True)
    assert is_news_subscribed(test_chat_id) is True
    assert test_chat_id in get_news_subscribers()

    set_news_subscriber(test_chat_id, False)
    assert is_news_subscribed(test_chat_id) is False
    assert test_chat_id not in get_news_subscribers()


def test_macro_news_card():
    items = [
        {
            "guid": "test-1",
            "title": "Nghị định 55 về chứng khoán",
            "link": "https://cafef.vn/tin1",
            "category": "CHÍNH SÁCH - PHÁP LUẬT",
            "summary": "Quy định mới về giao dịch ký quỹ",
            "published_at": "2026-09-22T08:30:00+00:00",
            "source": "CafeF",
        },
        {
            "guid": "test-2",
            "title": "VNINDEX tăng mạnh 17 điểm",
            "link": "https://cafef.vn/tin2",
            "category": "VĨ MÔ & THỊ TRƯỜNG",
            "summary": "Khối ngoại mua ròng trở lại",
            "published_at": "2026-09-22T09:00:00+00:00",
            "source": "VnExpress",
        },
    ]

    card = macro_news_card(items, title_suffix="1 Giờ Qua")
    assert "TỔNG HỢP TIN THỊ TRƯỜNG & VĂN BẢN PHÁP LUẬT" in card
    assert "Nghị định 55 về chứng khoán" in card
    assert "VNINDEX tăng mạnh 17 điểm" in card
    assert "href=\"https://cafef.vn/tin1\"" in card
    assert "/tintuc on" in card
