"""Quet cuoi phien va sinh canh bao cho danh sach theo doi.

Giai quyet van de: nguoi dung theo doi nhieu ma khong the ngoi doc lai
khuyen nghi tung ma moi ngay. Sau gio dong cua, run_eod_scan() tinh lai
khuyen nghi cho MOI ma dang duoc it nhat mot nguoi theo doi, so voi trang
thai da luu lan truoc, va CHI tra ve canh bao khi co thay doi dang chu y -
tranh lam phien nguoi dung voi tin nhan lap lai.

Module nay KHONG goi Telegram API - tra ve list[EodAlert] de bot/main.py
(hoac scheduler) tu gui. Trang thai duoc luu vao bang `signals` (cot
payload dang JSON) da co san trong data/cache.py, side='eod'.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..analysis.scoring import Recommendation, recommend
from ..data.cache import connect
from ..data.router import DataRouter, get_router
from ..indicators.common import volume_ratio
from ..indicators.ichimoku import ichimoku_state
from ..indicators.macd import macd_state
from ..indicators.rsi import rsi_state
from ..logging_conf import get_logger
from . import watchlist

log = get_logger(__name__)

_MAX_ALERTS_PER_SYMBOL_PER_DAY = 3
_VOLUME_SPIKE_RATIO = 2.0
_BIG_MOVE_PCT = 0.04
_MIN_BARS = 60


@dataclass
class EodAlert:
    """Mot tin nhan can gui cho mot chat_id, da GOP het cac ma co thay doi."""

    chat_id: int
    lines: list[str] = field(default_factory=list)


def _load_previous_state(symbol: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM signals WHERE symbol = ? AND side = 'eod' "
            "ORDER BY trade_date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    if row is None or not row["payload"]:
        return None
    try:
        return json.loads(row["payload"])
    except (TypeError, ValueError):
        return None


def _save_state(symbol: str, state: dict, rec: Recommendation) -> None:
    today = date.today().isoformat()
    payload = json.dumps(state, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            "INSERT INTO signals(trade_date, symbol, side, probability, entry, "
            "stop_loss, target, payload) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(trade_date, symbol, side) DO UPDATE SET "
            "entry=excluded.entry, stop_loss=excluded.stop_loss, "
            "target=excluded.target, payload=excluded.payload",
            (today, symbol, "eod", None, rec.close, rec.stop_loss, rec.target, payload),
        )


def _detect_significant_change(
    previous: dict | None, today: dict, vol_ratio: float | None, day_change_pct: float
) -> list[str]:
    """Doi chieu trang thai hom nay voi lan quet truoc, tra ve LY DO thay doi.

    Danh sach rong nghia la khong co gi dang chu y (hoac day la lan dau thay
    ma nay, chua co gi de so sanh) - khong gui canh bao.
    """
    if previous is None:
        return []

    reasons: list[str] = []

    if previous.get("action") != today["action"]:
        reasons.append(f"Khuyến nghị đổi từ {previous.get('action')} sang {today['action']}")

    cross = today.get("macd_cross")
    if cross is not None and cross != previous.get("macd_cross"):
        huong = "vàng (tăng)" if cross == "golden" else "chết (giảm)"
        reasons.append(f"MACD vừa giao cắt {huong}")

    kumo_pos = today.get("price_vs_kumo")
    if kumo_pos is not None and kumo_pos != previous.get("price_vs_kumo"):
        label = kumo_pos.replace("_", " ")
        reasons.append(f"Giá vừa chuyển sang vị trí {label} so với mây Kumo")

    extreme_zones = ("qua_mua", "qua_ban")
    prev_zone, cur_zone = previous.get("rsi_zone"), today.get("rsi_zone")
    if cur_zone != prev_zone and (cur_zone in extreme_zones or prev_zone in extreme_zones):
        reasons.append(f"RSI vừa chuyển vùng {prev_zone or 'n/a'} → {cur_zone or 'n/a'}")

    if vol_ratio is not None and vol_ratio > _VOLUME_SPIKE_RATIO:
        reasons.append(f"Khối lượng đột biến {vol_ratio:.1f} lần trung bình 20 phiên")

    if abs(day_change_pct) > _BIG_MOVE_PCT:
        reasons.append(f"Giá biến động {day_change_pct:+.1%} trong phiên")

    return reasons


def _format_change_lines(symbol: str, rec: Recommendation, reasons: list[str]) -> list[str]:
    lines = [f"<b>{symbol}</b> — {rec.action} (điểm {rec.total_score:+.0f})"]
    lines.extend(f"  • {reason}" for reason in reasons)
    return lines


def _scan_one_symbol(symbol: str, router: DataRouter) -> list[str] | None:
    """Tinh lai khuyen nghi cho mot ma, so sanh va luu trang thai moi.

    Tra ve cac dong mo ta thay doi (de gop vao tin nhan) neu CAN canh bao,
    None neu khong co gi dang chu y hoac da dat gioi han canh bao/ngay.
    """
    end = date.today()
    frame = router.ohlcv(symbol, end - timedelta(days=400), end)
    if len(frame) < _MIN_BARS:
        return None

    rec = recommend(frame, symbol)
    macd_st = macd_state(frame)
    rsi_st = rsi_state(frame)
    ichi_st = ichimoku_state(frame)

    vr_series = volume_ratio(frame, period=20).dropna()
    vol_ratio = float(vr_series.iloc[-1]) if not vr_series.empty else None

    close = float(frame["close"].iloc[-1])
    prev_close = float(frame["close"].iloc[-2]) if len(frame) > 1 else close
    day_change_pct = (close / prev_close - 1) if prev_close else 0.0

    previous = _load_previous_state(symbol)
    reasons = _detect_significant_change(previous, {
        "action": rec.action,
        "macd_cross": macd_st.get("cross"),
        "price_vs_kumo": ichi_st.get("price_vs_kumo"),
        "rsi_zone": rsi_st.get("zone"),
    }, vol_ratio, day_change_pct)

    # Dem theo NGAY: trang thai truoc la cua hom qua thi dem lai tu 0. Ban cu
    # cong don qua cac ngay nen sau 3 ngay co canh bao, ma do im lang mai mai.
    today = date.today().isoformat()
    same_day = previous is not None and previous.get("scan_date") == today
    alerts_sent_today = previous.get("alerts_sent_today", 0) if same_day else 0
    should_alert = bool(reasons) and alerts_sent_today < _MAX_ALERTS_PER_SYMBOL_PER_DAY

    new_state = {
        "action": rec.action,
        "macd_cross": macd_st.get("cross"),
        "price_vs_kumo": ichi_st.get("price_vs_kumo"),
        "rsi_zone": rsi_st.get("zone"),
        "close": close,
        "scan_date": today,
        "alerts_sent_today": alerts_sent_today + 1 if should_alert else alerts_sent_today,
    }
    _save_state(symbol, new_state, rec)

    return _format_change_lines(symbol, rec, reasons) if should_alert else None


def run_eod_scan() -> list[EodAlert]:
    """Quet toan bo ma dang duoc theo doi, tra ve canh bao GOP theo chat_id.

    Moi chat_id chi nhan TOI DA mot EodAlert (nhieu ma co thay doi duoc gop
    thanh mot tin nhan duy nhat), va chi khi chat_id do dang BAT canh bao
    tu dong (xem alerts/watchlist.py:is_alerts_enabled).
    """
    router = get_router()
    subs = watchlist.all_subscriptions()
    watched_symbols = sorted({symbol for _, symbol in subs})

    changes: dict[str, list[str]] = {}
    for symbol in watched_symbols:
        try:
            lines = _scan_one_symbol(symbol, router)
        except Exception as exc:
            log.warning("eod scan: bo qua %s do loi: %s", symbol, exc)
            continue
        if lines:
            changes[symbol] = lines

    if not changes:
        log.info("eod scan: quet %d ma, khong co thay doi dang chu y", len(watched_symbols))
        return []

    symbols_by_chat: dict[int, list[str]] = {}
    for chat_id, symbol in subs:
        if symbol in changes:
            symbols_by_chat.setdefault(chat_id, []).append(symbol)

    alerts: list[EodAlert] = []
    for chat_id, symbols in symbols_by_chat.items():
        if not watchlist.is_alerts_enabled(chat_id):
            continue
        lines: list[str] = []
        for symbol in sorted(symbols):
            lines.extend(changes[symbol])
        alerts.append(EodAlert(chat_id=chat_id, lines=lines))

    log.info(
        "eod scan: %d/%d ma co thay doi, gui cho %d chat",
        len(changes), len(watched_symbols), len(alerts),
    )
    return alerts
