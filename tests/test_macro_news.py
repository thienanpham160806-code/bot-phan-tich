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


def test_classify_ignores_non_legal_uses_of_luat():
    assert classify_news("Cán bộ bị kỷ luật vì vi phạm", "") == "DOANH NGHIỆP & NGÀNH"
    assert classify_news("Luật sư tư vấn thừa kế", "") == "DOANH NGHIỆP & NGÀNH"
    assert classify_news("Quốc hội thông qua Luật Chứng khoán sửa đổi", "") == (
        "CHÍNH SÁCH - PHÁP LUẬT"
    )
    assert classify_news("Tôi quyết định nghỉ việc", "") == "DOANH NGHIỆP & NGÀNH"
    assert classify_news("Quyết định 123/QĐ-TTg về đầu tư công", "") == "CHÍNH SÁCH - PHÁP LUẬT"


def test_market_relevance_filter():
    from bot_phan_tich.data.macro_news import is_market_relevant

    assert not is_market_relevant("Cầu Nhật Tân xuất hiện loạt biển báo mới", "")
    assert is_market_relevant("Lãi suất huy động giảm", "")


def test_select_broadcast_items_only_recent_newest_first():
    from datetime import timedelta

    from bot_phan_tich.data.macro_news import select_broadcast_items

    now = datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc)
    items = [
        {"guid": "old", "published_at": (now - timedelta(hours=20)).isoformat()},
        {"guid": "a", "published_at": (now - timedelta(minutes=90)).isoformat()},
        {"guid": "b", "published_at": (now - timedelta(minutes=10)).isoformat()},
        {"guid": "broken", "published_at": "khong-phai-ngay"},
    ]
    assert [it["guid"] for it in select_broadcast_items(items, now=now)] == ["b", "a"]


def test_seed_subscribers_keeps_explicit_opt_out(isolated_db):
    set_news_subscriber(2, False)
    cache.seed_subscribers([1, 2, -1001])
    assert sorted(get_news_subscribers()) == [-1001, 1]


def test_auto_subscribe_chat_ids_parsing(monkeypatch):
    from bot_phan_tich.config import auto_subscribe_chat_ids

    monkeypatch.setenv("AUTO_SUBSCRIBE_CHAT_IDS", " 123, -100456 ,abc,, 7")
    assert auto_subscribe_chat_ids() == [123, -100456, 7]


def _tg_message(chat_id: int, text: str = "/kn FPT"):
    from aiogram.types import Chat, Message

    return Message(
        message_id=1, date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="private"), text=text,
    )


def test_any_message_auto_subscribes_news_but_respects_opt_out(isolated_db):
    import asyncio

    from aiogram.types import CallbackQuery, User

    from bot_phan_tich.bot.main import AutoSubscribeNews

    calls = []

    async def handler(event, data):
        calls.append(event)
        return "ok"

    middleware = AutoSubscribeNews()
    set_news_subscriber(2, False)  # da chu dong /tintuc off truoc do
    callback = CallbackQuery(
        id="q", from_user=User(id=3, is_bot=False, first_name="A"),
        chat_instance="c", data="screen:breakout", message=_tg_message(3),
    )

    async def run():
        for event in (_tg_message(1), _tg_message(1), _tg_message(2), callback):
            assert await middleware(handler, event, {}) == "ok"

    asyncio.run(run())
    assert len(calls) == 4  # lenh cua nguoi dung van chay binh thuong
    assert sorted(get_news_subscribers()) == [1, 3]
    assert is_news_subscribed(2) is False


def test_auto_subscribe_failure_does_not_block_command(monkeypatch):
    import asyncio

    from bot_phan_tich.bot import main

    def broken(_ids):
        raise RuntimeError("CSDL hong")

    monkeypatch.setattr(main, "seed_subscribers", broken)

    async def handler(event, data):
        return "ok"

    result = asyncio.run(main.AutoSubscribeNews()(handler, _tg_message(9), {}))
    assert result == "ok"
