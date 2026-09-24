"""Quan ly danh sach ma theo doi va cong/tat canh bao tu dong cho tung chat_id.

Dung lai bang `subscriptions` va `alert_settings` da co san trong
data/cache.py - module nay chi la lop nghiep vu goi vao do (them/xoa/liet
ke), khong tu mo ket noi mang.
"""
from __future__ import annotations

import time

from ..data.cache import connect
from ..logging_conf import get_logger

log = get_logger(__name__)


def add(chat_id: int, symbol: str) -> None:
    """Them mot ma vao danh sach theo doi cua chat_id. Bo qua neu da theo doi roi."""
    symbol = symbol.upper()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO subscriptions(chat_id, symbol, created_at) VALUES (?,?,?)",
            (chat_id, symbol, time.time()),
        )
    log.info("chat %s theo doi %s", chat_id, symbol)


def seed(chat_ids: list[int], symbols: list[str]) -> None:
    """Them `symbols` vao danh sach theo doi cua tung chat trong `chat_ids`
    (bo qua ma da co). Goi luc khoi dong voi AUTO_SUBSCRIBE_CHAT_IDS +
    AUTO_WATCHLIST: Render Free xoa CSDL moi lan restart, mat het /sub."""
    if not chat_ids or not symbols:
        return
    now = time.time()
    with connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO subscriptions(chat_id, symbol, created_at) VALUES (?,?,?)",
            [(chat_id, symbol.upper(), now) for chat_id in chat_ids for symbol in symbols],
        )
    log.info("tu them %d ma vao danh sach theo doi cua %d chat", len(symbols), len(chat_ids))


def remove(chat_id: int, symbol: str) -> None:
    """Bo theo doi mot ma. Khong bao loi neu chua theo doi tu truoc."""
    symbol = symbol.upper()
    with connect() as conn:
        conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND symbol = ?", (chat_id, symbol)
        )
    log.info("chat %s bo theo doi %s", chat_id, symbol)


def list_symbols(chat_id: int) -> list[str]:
    """Danh sach ma dang theo doi cua mot chat_id, sap xep theo ten."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT symbol FROM subscriptions WHERE chat_id = ? ORDER BY symbol", (chat_id,)
        ).fetchall()
    return [r["symbol"] for r in rows]


def subscribers_of(symbol: str) -> list[int]:
    """Danh sach chat_id dang theo doi mot ma - dung khi day canh bao."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM subscriptions WHERE symbol = ?", (symbol.upper(),)
        ).fetchall()
    return [int(r["chat_id"]) for r in rows]


def all_subscriptions() -> list[tuple[int, str]]:
    """Toan bo cap (chat_id, symbol) hien co - dung de quet EOD mot lan cho tat ca."""
    with connect() as conn:
        rows = conn.execute("SELECT chat_id, symbol FROM subscriptions").fetchall()
    return [(int(r["chat_id"]), r["symbol"]) for r in rows]


def is_alerts_enabled(chat_id: int) -> bool:
    """Mac dinh BAT canh bao khi chat_id chua tung bam /canhbao lan nao."""
    with connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM alert_settings WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return True if row is None else bool(row["enabled"])


def set_alerts_enabled(chat_id: int, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO alert_settings(chat_id, enabled) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled",
            (chat_id, int(enabled)),
        )
    log.info("chat %s dat canh bao tu dong = %s", chat_id, enabled)


def toggle_alerts(chat_id: int) -> bool:
    """Dao trang thai bat/tat, tra ve trang thai MOI (dung cho lenh /canhbao)."""
    new_state = not is_alerts_enabled(chat_id)
    set_alerts_enabled(chat_id, new_state)
    return new_state
