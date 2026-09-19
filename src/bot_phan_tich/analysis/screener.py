"""Loc co phieu theo dieu kien ky thuat va co ban.

Giai quyet van de: nguoi dung can quet nhanh mot phan hay toan bo san de tim
ma dat dieu kien, MA KHONG duoc lam bot treo. Vi vay:
  - Quet tren du lieu OHLCV da co trong cache (data/router.py tu lo viec doc
    cache truoc khi goi mang).
  - Co gioi han thoi gian `screener.timeout_seconds` - qua han thi dung va
    tra ve ket qua da quet duoc kem ghi chu, khong quet tiep.
  - Ghi log tien do dinh ky de theo doi mot lan quet dai dang chay den dau.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import get_settings
from ..data.router import DataRouter, get_router
from ..data.universe import liquid_universe
from ..indicators.common import volume_ratio
from ..indicators.divergence import detect_divergence
from ..indicators.ichimoku import ichimoku_state
from ..indicators.macd import macd, macd_state
from ..indicators.rsi import rsi_state
from ..logging_conf import get_logger
from .lookup import _RATIO_COLUMN_MAP, _extract, _industry_column
from .scoring import (
    ACTION_ACCUMULATE,
    ACTION_BUY,
    ACTION_REDUCE,
    ACTION_SELL,
    ACTION_WATCH,
    recommend,
)

log = get_logger(__name__)

_ACTION_RANK = {
    ACTION_SELL: 0,
    ACTION_REDUCE: 1,
    ACTION_WATCH: 2,
    ACTION_ACCUMULATE: 3,
    ACTION_BUY: 4,
}
_MIN_BARS = 60
_PROGRESS_LOG_EVERY = 50


@dataclass
class ScreenCriteria:
    """Dieu kien loc. Tat ca cac truong deu tuy chon (None = khong loc theo do)."""

    symbols: list[str] | None = None  # None = quet toan vu tru thanh khoan (data/universe.py)

    # --- ky thuat ---
    min_action: str | None = None  # vd ACTION_ACCUMULATE -> chi lay tu bac nay len
    min_total_score: float | None = None
    price_vs_kumo: str | None = None  # "tren_may" / "trong_may" / "duoi_may"
    macd_cross: str | None = None  # "golden" / "death"
    rsi_zone: str | None = None  # "qua_mua" / "trung_tinh" / "qua_ban"
    require_bullish_divergence: bool = False
    require_bearish_divergence: bool = False
    min_volume_ratio: float | None = None
    max_volume_ratio: float | None = None
    alert_mode: bool = False  # bo loc "canh bao": duoi may HOAC phan ky am (OR, khong phai AND)

    # --- co ban ---
    pe_min: float | None = None
    pe_max: float | None = None
    pb_min: float | None = None
    pb_max: float | None = None
    min_roe: float | None = None
    min_market_cap: float | None = None
    exchanges: list[str] | None = None
    industries: list[str] | None = None


@dataclass
class ScreenResult:
    symbol: str
    action: str
    total_score: float
    close: float
    component_scores: dict[str, float]
    reasons: list[str]


@dataclass
class ScreenReport:
    """Ket qua mot lan quet, kem ghi chu neu bi cat ngang do het thoi gian."""

    results: list[ScreenResult]
    scanned: int
    total: int
    timed_out: bool
    note: str | None = field(default=None)


def preset_breakout() -> ScreenCriteria:
    """"Dot pha": gia vua vuot len tren may Kumo, MACD giao cat tang, KL > 1.5x TB20."""
    return ScreenCriteria(price_vs_kumo="tren_may", macd_cross="golden", min_volume_ratio=1.5)


def preset_accumulate() -> ScreenCriteria:
    """"Tich luy": gia trong may (may mong), RSI trung tinh, khoi luong can."""
    return ScreenCriteria(price_vs_kumo="trong_may", rsi_zone="trung_tinh", max_volume_ratio=0.8)


def preset_warning() -> ScreenCriteria:
    """"Canh bao": gia thung xuong duoi may Kumo HOAC co phan ky am (dieu kien OR)."""
    return ScreenCriteria(alert_mode=True)


def _passes_technical(
    ichi_state: dict, rsi_state_: dict, divergence: dict, vol_ratio: float | None,
    total_score: float, action: str, criteria: ScreenCriteria,
) -> bool:
    if criteria.alert_mode:
        return ichi_state.get("price_vs_kumo") == "duoi_may" or divergence.get("type") == "bearish"

    if criteria.min_action:
        wanted_rank = _ACTION_RANK.get(criteria.min_action, 0)
        if _ACTION_RANK.get(action, -1) < wanted_rank:
            return False
    if criteria.min_total_score is not None and total_score < criteria.min_total_score:
        return False
    if criteria.price_vs_kumo and ichi_state.get("price_vs_kumo") != criteria.price_vs_kumo:
        return False
    # criteria.macd_cross duoc kiem rieng o _evaluate_symbol() truoc khi goi ham nay,
    # vi can macd_state() (khong nam trong cac tham so cua ham nay).
    if criteria.rsi_zone and rsi_state_.get("zone") != criteria.rsi_zone:
        return False
    if criteria.require_bullish_divergence and divergence.get("type") != "bullish":
        return False
    if criteria.require_bearish_divergence and divergence.get("type") != "bearish":
        return False
    min_vr, max_vr = criteria.min_volume_ratio, criteria.max_volume_ratio
    if min_vr is not None and (vol_ratio is None or vol_ratio < min_vr):
        return False
    if max_vr is not None and (vol_ratio is None or vol_ratio > max_vr):
        return False
    return True


def _passes_fundamental(symbol: str, criteria: ScreenCriteria, router: DataRouter) -> bool:
    has_fundamental_filter = any(
        [
            criteria.pe_min, criteria.pe_max, criteria.pb_min, criteria.pb_max,
            criteria.min_roe, criteria.min_market_cap, criteria.industries,
        ]
    )
    if not has_fundamental_filter:
        return True  # khong loc theo co ban -> khong can goi them du lieu (nhanh hon)

    if criteria.industries:
        industry = _peer_industry(symbol, router)
        if industry not in criteria.industries:
            return False

    pe = pb = roe = None
    try:
        ratios = router.financials(symbol, period="year").get("ratios")
        if ratios is not None and not ratios.empty:
            row = ratios.iloc[-1]
            pe = _extract(row, _RATIO_COLUMN_MAP["pe"])
            pb = _extract(row, _RATIO_COLUMN_MAP["pb"])
            roe = _extract(row, _RATIO_COLUMN_MAP["roe"])
    except Exception as exc:
        log.debug("screen(): khong lay duoc ratios cho %s: %s", symbol, exc)

    if criteria.pe_min is not None and (pe is None or pe < criteria.pe_min):
        return False
    if criteria.pe_max is not None and (pe is None or pe > criteria.pe_max):
        return False
    if criteria.pb_min is not None and (pb is None or pb < criteria.pb_min):
        return False
    if criteria.pb_max is not None and (pb is None or pb > criteria.pb_max):
        return False
    if criteria.min_roe is not None and (roe is None or roe < criteria.min_roe):
        return False

    if criteria.min_market_cap is not None:
        # Can company_overview() (so luong CP luu hanh) - hien chua co nguon
        # xac nhan (xem data/base.py). Khong bia so: coi nhu khong dat dieu
        # kien khi thieu du lieu, thay vi gia dinh dat.
        market_cap = _market_cap(symbol, router)
        if market_cap is None or market_cap < criteria.min_market_cap:
            return False

    return True


def _peer_industry(symbol: str, router: DataRouter) -> str | None:
    try:
        industry_map = router.industry_map()
        col = _industry_column(industry_map)
        if not col:
            return None
        row = industry_map.loc[industry_map["symbol"].astype(str).str.upper() == symbol]
        return str(row.iloc[0][col]) if not row.empty else None
    except Exception:
        return None


def _market_cap(symbol: str, router: DataRouter) -> float | None:
    try:
        shares = router.company_overview(symbol).get("shares_outstanding")
        if not shares:
            return None
        end = date.today()
        frame = router.ohlcv(symbol, end - timedelta(days=10), end)
        if frame.empty:
            return None
        return float(frame["close"].iloc[-1]) * float(shares)
    except Exception:
        return None


def _evaluate_symbol(
    symbol: str, frame, criteria: ScreenCriteria, router: DataRouter
) -> ScreenResult | None:
    if len(frame) < _MIN_BARS:
        return None

    rec = recommend(frame, symbol)
    rsi_st = rsi_state(frame)
    ichi_st = ichimoku_state(frame)
    divergence = detect_divergence(frame, macd(frame)["hist"])
    vr_series = volume_ratio(frame, period=20).dropna()
    vr_last = float(vr_series.iloc[-1]) if not vr_series.empty else None

    if criteria.macd_cross:
        macd_st = macd_state(frame)
        if macd_st.get("cross") != criteria.macd_cross:
            return None

    ok_technical = _passes_technical(
        ichi_st, rsi_st, divergence, vr_last, rec.total_score, rec.action, criteria
    )
    if not ok_technical:
        return None
    if not _passes_fundamental(symbol, criteria, router):
        return None

    return ScreenResult(
        symbol=symbol,
        action=rec.action,
        total_score=rec.total_score,
        close=rec.close,
        component_scores=rec.component_scores,
        reasons=rec.reasons,
    )


def screen_report(criteria: ScreenCriteria) -> ScreenReport:
    """Chay mot lan quet day du, tra ve ket qua kem thong tin tien do/timeout."""
    settings = get_settings()
    timeout = settings.get("screener.timeout_seconds", 25.0)
    router = get_router()

    symbols = criteria.symbols or liquid_universe(use_watchlist=False)
    if criteria.exchanges:
        try:
            listing = router.listing(criteria.exchanges)
            allowed = set(listing["symbol"].astype(str).str.upper())
            symbols = [s for s in symbols if s in allowed]
        except Exception as exc:
            log.warning("screen(): khong loc duoc truoc theo san: %s", exc)

    total = len(symbols)
    end = date.today()
    start_range = end - timedelta(days=400)

    started = time.monotonic()
    results: list[ScreenResult] = []
    scanned = 0
    timed_out = False

    for symbol in symbols:
        if time.monotonic() - started > timeout:
            timed_out = True
            log.warning("screen(): het han %.0fs sau %d/%d ma, dung quet", timeout, scanned, total)
            break

        scanned += 1
        if scanned % _PROGRESS_LOG_EVERY == 0 or scanned == total:
            log.info(
                "screen(): da quet %d/%d ma (%d ma hop dieu kien)", scanned, total, len(results)
            )

        try:
            frame = router.ohlcv(symbol, start_range, end)
            result = _evaluate_symbol(symbol, frame, criteria, router)
            if result is not None:
                results.append(result)
        except Exception as exc:
            log.debug("screen(): bo qua %s do loi: %s", symbol, exc)

    results.sort(key=lambda r: r.total_score, reverse=True)
    note = None
    if timed_out:
        note = f"Chua quet het: da quet {scanned}/{total} ma trong {timeout:.0f}s cho phep."

    return ScreenReport(
        results=results, scanned=scanned, total=total, timed_out=timed_out, note=note
    )


def screen(criteria: ScreenCriteria) -> list[ScreenResult]:
    """Loc co phieu theo `criteria`. Xem screen_report() de lay them ghi chu timeout."""
    return screen_report(criteria).results
