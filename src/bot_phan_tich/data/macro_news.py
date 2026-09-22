"""Thu thap va phan loai tin tuc vi mo, phap luat, nghi dinh, thi truong tu RSS."""
from __future__ import annotations

import email.utils
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

from ..logging_conf import get_logger

log = get_logger(__name__)

# Danh sach cac nguon RSS uy tin
DEFAULT_FEEDS = [
    {
        "url": "https://cafef.vn/vi-mo-dau-tu.rss",
        "source": "CafeF Vĩ mô",
        "default_cat": "CHÍNH SÁCH - PHÁP LUẬT",
    },
    {
        "url": "https://cafef.vn/thi-truong-chung-khoan.rss",
        "source": "CafeF TTCK",
        "default_cat": "VĨ MÔ & THỊ TRƯỜNG",
    },
    {
        "url": "https://cafef.vn/tai-chinh-ngan-hang.rss",
        "source": "CafeF Tài chính",
        "default_cat": "VĨ MÔ & THỊ TRƯỜNG",
    },
    {
        "url": "https://vnexpress.net/rss/kinh-doanh.rss",
        "source": "VnExpress",
        "default_cat": "VĨ MÔ & THỊ TRƯỜNG",
    },
]

# Tu khoa nhan dien van ban phap quy, nghi dinh, nghi quyet
POLICY_KEYWORDS = [
    "nghị định",
    "nghị quyết",
    "thông tư",
    "luật",
    "dự thảo",
    "chính phủ",
    "thủ tướng",
    "bộ tài chính",
    "ngân hàng nhà nước",
    "nhnn",
    "ubck",
    "ủy ban chứng khoán",
    "quyết định",
    "chính sách",
    "văn bản",
    "chỉ thị",
]

# Tu khoa thi truong tai chinh, vi mo
MACRO_KEYWORDS = [
    "lãi suất",
    "tỷ giá",
    "gdp",
    "cpi",
    "lạm phát",
    "tín dụng",
    "trái phiếu",
    "nâng hạng",
    "fdi",
    "khối ngoại",
    "vnindex",
    "chứng khoán",
    "thanh khoản",
    "tiền tệ",
    "xuất nhập khẩu",
]


@dataclass
class MacroNewsItem:
    guid: str
    title: str
    link: str
    category: str
    summary: str
    published_at: datetime
    source: str

    def to_dict(self) -> dict:
        return {
            "guid": self.guid,
            "title": self.title,
            "link": self.link,
            "category": self.category,
            "summary": self.summary,
            "published_at": self.published_at.isoformat(),
            "source": self.source,
        }


def classify_news(title: str, summary: str, default_cat: str = "DOANH NGHIỆP & NGÀNH") -> str:
    """Phan loai tin dua tren tieu de va noi dung tom tat."""
    text = f"{title} {summary}".lower()
    for kw in POLICY_KEYWORDS:
        if kw in text:
            return "CHÍNH SÁCH - PHÁP LUẬT"
    for kw in MACRO_KEYWORDS:
        if kw in text:
            return "VĨ MÔ & THỊ TRƯỜNG"
    return default_cat or "DOANH NGHIỆP & NGÀNH"


def clean_html(raw_html: str | None) -> str:
    """Loai bo the HTML, anh, ky tu rac khoi doan mo ta RSS."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_rfc822_date(date_str: str | None) -> datetime:
    """Chuyen doi chuoi pubDate sang datetime UTC."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def fetch_feed_items(
    feed_url: str,
    source_name: str,
    default_cat: str = "VĨ MÔ & THỊ TRƯỜNG",
    timeout: int = 8,
) -> list[MacroNewsItem]:
    """Tai va phan tich cac bai viet tu mot duong dan RSS."""
    req = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    items: list[MacroNewsItem] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
        tree = ET.fromstring(content)
        for item in tree.findall(".//item"):
            title_node = item.find("title")
            link_node = item.find("link")
            desc_node = item.find("description")
            pub_node = item.find("pubDate")
            guid_node = item.find("guid")

            title = clean_html(title_node.text if title_node is not None else "")
            link = (link_node.text or "").strip() if link_node is not None else ""
            if not title or not link:
                continue

            summary = clean_html(desc_node.text if desc_node is not None else "")
            if len(summary) > 180:
                summary = summary[:177] + "..."

            pub_date = parse_rfc822_date(pub_node.text if pub_node is not None else None)
            guid = (guid_node.text or link).strip() if guid_node is not None else link

            cat = classify_news(title, summary, default_cat)
            items.append(
                MacroNewsItem(
                    guid=guid,
                    title=title,
                    link=link,
                    category=cat,
                    summary=summary,
                    published_at=pub_date,
                    source=source_name,
                )
            )
    except Exception as exc:
        log.warning("Loi khi tai RSS %s (%s): %s", source_name, feed_url, exc)
    return items


def fetch_all_macro_news() -> list[MacroNewsItem]:
    """Tai tat ca cac nguon RSS va sap xep theo thoi gian moi nhat."""
    all_items: list[MacroNewsItem] = []
    seen_links: set[str] = set()

    for feed in DEFAULT_FEEDS:
        items = fetch_feed_items(feed["url"], feed["source"], feed["default_cat"])
        for it in items:
            if it.link not in seen_links:
                seen_links.add(it.link)
                all_items.append(it)

    all_items.sort(key=lambda x: x.published_at, reverse=True)
    return all_items
