"""Ban tin bien dong thi truong va tac dong len cac ma dang theo doi (/biendong).

Hai phan:
  1. Thi truong: VN-Index, VN30 (nen ngay tu gap-chart - co ca nen DANG CHAY
     cua phien hom nay), do rong (so ma tang/giam) va khoi ngoai tren vu tru
     thanh khoan (bang gia Vietcap, ~3 request cho ~200 ma).
  2. Tac dong len ma theo doi: tach bien dong hom nay cua moi ma thanh
       phan thi truong = beta x %VN-Index
       phan rieng      = %ma - phan thi truong
     beta = cov(r_ma, r_index) / var(r_index) tren toi da 120 phien gan
     nhat (loi suat ngay, bo cac phien |r| > 15% - thuong la chia tach/
     quyen, khong phai bien dong that). Xem docs/cong-thuc.md muc 10.

Module nay KHONG dung toi chi bao/cham diem/bo loc (analysis/scoring.py,
screener.py) - chi them thong tin, khong doi ket qua khuyen nghi.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from ..config import get_universe_config, now_local
from ..data import market_store
from ..logging_conf import get_logger

log = get_logger(__name__)

BETA_WINDOW = 120  # so phien toi da dung tinh beta
BETA_MIN_OBS = 40  # it hon so phien nay thi khong tinh beta (khong dang tin)
MAX_ABS_DAILY_RETURN = 0.15  # |r| lon hon: coi la chia tach/quyen, bo qua
OWN_MOVE_THRESHOLD = 0.005  # |phan rieng| duoi 0,5% coi nhu "di cung thi truong"
LOW_CORRELATION = 0.3
_INDEX_COUNT_BACK = BETA_WINDOW + 40
_TOP_MOVERS = 3


@dataclass
class IndexMove:
    symbol: str
    session_date: date
    close: float
    change_pts: float
    change_pct: float
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    avg_volume_20: float | None = None


@dataclass
class Breadth:
    total: int
    advancers: int
    decliners: int
    unchanged: int
    top_gainers: list[tuple[str, float]] = field(default_factory=list)
    top_losers: list[tuple[str, float]] = field(default_factory=list)
    foreign_net_value: float | None = None  # VND, duong = mua rong


@dataclass
class SymbolImpact:
    symbol: str
    price: float
    change_pct: float
    beta: float | None = None
    correlation: float | None = None
    market_part: float | None = None
    own_part: float | None = None
    foreign_net_value: float | None = None

    @property
    def verdict(self) -> str:
        if self.own_part is None:
            return "chưa đủ lịch sử để tính beta"
        if self.correlation is not None and self.correlation < LOW_CORRELATION:
            return "ít chịu ảnh hưởng của thị trường (tương quan thấp)"
        if self.own_part > OWN_MOVE_THRESHOLD:
            return "mạnh hơn thị trường"
        if self.own_part < -OWN_MOVE_THRESHOLD:
            return "yếu hơn thị trường"
        return "đi cùng thị trường"


@dataclass
class MarketPulse:
    as_of: datetime
    live: bool  # True: co nen cua phien HOM NAY (dang/vua giao dich)
    index: IndexMove
    vn30: IndexMove | None
    breadth: Breadth | None
    impacts: dict[str, SymbolImpact]
    missing: list[str] = field(default_factory=list)  # ma khong lay duoc gia


# ------------------------------------------------------------------ tinh toan
def daily_returns(close: pd.Series) -> pd.Series:
    """Loi suat ngay, bo cac phien bien dong bat thuong (MAX_ABS_DAILY_RETURN)."""
    returns = close.sort_index().pct_change().dropna()
    return returns[returns.abs() <= MAX_ABS_DAILY_RETURN]


def beta_vs_index(
    stock_close: pd.Series, index_close: pd.Series,
    window: int = BETA_WINDOW, min_obs: int = BETA_MIN_OBS,
) -> tuple[float | None, float | None]:
    """(beta, he so tuong quan) cua ma so voi chi so - hai chuoi gia dong cua
    danh chi muc theo NGAY. (None, None) neu chua du `min_obs` phien chung."""
    joined = pd.concat(
        {"s": daily_returns(stock_close), "i": daily_returns(index_close)},
        axis=1, join="inner",
    ).tail(window)
    if len(joined) < min_obs:
        return None, None
    var = joined["i"].var()
    if not var:
        return None, None
    beta = float(joined["s"].cov(joined["i"]) / var)
    corr = float(joined["s"].corr(joined["i"]))
    return beta, corr


def decompose(
    change_pct: float, beta: float | None, index_change_pct: float
) -> tuple[float | None, float | None]:
    """(phan do thi truong, phan rieng cua ma) cua bien dong hom nay."""
    if beta is None:
        return None, None
    market_part = beta * index_change_pct
    return market_part, change_pct - market_part


def compute_breadth(quotes: pd.DataFrame, top: int = _TOP_MOVERS) -> Breadth | None:
    """Do rong tu bang gia (cot symbol, change_pct, foreign_net_value). Ma chua
    khop lenh (gia 0) da bi loai o buoc lay bang gia."""
    if quotes.empty:
        return None
    change = quotes["change_pct"]
    ranked = quotes.sort_values("change_pct")
    foreign = quotes["foreign_net_value"].dropna()
    return Breadth(
        total=len(quotes),
        advancers=int((change > 0).sum()),
        decliners=int((change < 0).sum()),
        unchanged=int((change == 0).sum()),
        top_gainers=[
            (r.symbol, float(r.change_pct))
            for r in ranked.tail(top).iloc[::-1].itertuples() if r.change_pct > 0
        ],
        top_losers=[
            (r.symbol, float(r.change_pct))
            for r in ranked.head(top).itertuples() if r.change_pct < 0
        ],
        foreign_net_value=float(foreign.sum()) if not foreign.empty else None,
    )


def index_move(bars: pd.DataFrame, symbol: str) -> IndexMove | None:
    """Bien dong cua nen cuoi so voi nen truoc (bars: time, open..volume)."""
    if len(bars) < 2:
        return None
    bars = bars.sort_values("time")
    last, prev = bars.iloc[-1], bars.iloc[-2]
    prev_close = float(prev["close"])
    close = float(last["close"])
    history_volume = bars["volume"].iloc[-21:-1]
    return IndexMove(
        symbol=symbol,
        session_date=pd.Timestamp(last["time"]).date(),
        close=close,
        change_pts=close - prev_close,
        change_pct=(close / prev_close - 1) if prev_close else 0.0,
        high=float(last["high"]),
        low=float(last["low"]),
        volume=float(last["volume"]),
        avg_volume_20=float(history_volume.mean()) if not history_volume.empty else None,
    )


_EMPTY_CLOSES = pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def _close_by_date(frame: pd.DataFrame) -> pd.Series:
    series = frame.set_index(pd.to_datetime(frame["time"]).dt.normalize())["close"]
    return series[~series.index.duplicated(keep="last")].astype(float)


# ----------------------------------------------------------------- lay du lieu
def _col(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(float("nan"), index=frame.index)


def quotes_from_board(board: pd.DataFrame) -> pd.DataFrame:
    """Chuan hoa bang gia Vietcap (getList) thanh: symbol, price, ref_price,
    change_pct, foreign_net_value. Bo ma chua khop lenh trong phien (gia 0)."""
    if board.empty:
        return pd.DataFrame(columns=["symbol", "price", "ref_price", "change_pct",
                                     "foreign_net_value"])
    symbol = board.get("listingInfo.symbol", board.get("matchPrice.symbol"))
    if symbol is None:
        log.warning("bang gia Vietcap khong co cot ma - cau truc co the da doi")
        return quotes_from_board(pd.DataFrame())
    quotes = pd.DataFrame({
        "symbol": symbol.astype(str).str.upper(),
        "price": _col(board, "matchPrice.matchPrice"),
        "ref_price": _col(board, "matchPrice.referencePrice", "listingInfo.refPrice"),
        "foreign_net_value": (
            _col(board, "matchPrice.foreignBuyValue") - _col(board, "matchPrice.foreignSellValue")
        ),
    })
    quotes = quotes[(quotes["price"] > 0) & (quotes["ref_price"] > 0)].copy()
    quotes["change_pct"] = quotes["price"] / quotes["ref_price"] - 1
    return quotes.drop_duplicates("symbol").reset_index(drop=True)


def _breadth_universe() -> list[str]:
    """Vu tru tinh do rong: cac ma trong snapshot (vu tru thanh khoan), neu
    chua co thi danh sach theo doi mac dinh trong config/universe.yaml."""
    from .snapshot import load_snapshot  # tranh import vong

    snap = load_snapshot()
    if not snap.empty and "symbol" in snap.columns:
        return sorted(snap["symbol"].astype(str).str.upper().unique())
    return default_watchlist()


def default_watchlist() -> list[str]:
    return [s.upper() for s in get_universe_config().get("watchlist", [])]


def _stock_history(symbols: list[str]) -> dict[str, pd.Series]:
    """Gia dong cua theo ngay cho beta: doc kho truoc, ma nao thieu (kho rong
    ngay sau khi Render khoi dong lai) moi goi mang."""
    from ..data.vietcap import fetch_ohlcv_bulk  # tranh import vong

    history: dict[str, pd.Series] = {}
    stored = market_store.load_ohlcv(symbols, columns=["symbol", "time", "close"])
    for sym, group in stored.groupby("symbol", observed=True):
        history[str(sym)] = _close_by_date(group)
    missing = [s for s in symbols if len(history.get(s, ())) < BETA_MIN_OBS + 1]
    if missing:
        fetched = fetch_ohlcv_bulk(missing, count_back=_INDEX_COUNT_BACK)
        for sym, group in fetched.groupby("symbol"):
            history[str(sym)] = _close_by_date(group)
    return history


def build_market_pulse(watched: list[str]) -> MarketPulse:
    """Chup bien dong thi truong luc nay + tac dong len `watched`. Goi mang
    (~5-10 request) - chay trong thread rieng (asyncio.to_thread)."""
    from ..data.vietcap import _fetch_ohlcv_one, fetch_price_board

    benchmark = get_universe_config().get("benchmark", "VNINDEX")
    now = now_local()
    to_ts = int(time.time())

    index_bars = _fetch_ohlcv_one(benchmark, _INDEX_COUNT_BACK, to_ts)
    move = index_move(index_bars, benchmark) if index_bars is not None else None
    if move is None:
        raise RuntimeError(f"Không lấy được dữ liệu {benchmark} từ Vietcap")
    vn30_bars = _fetch_ohlcv_one("VN30", 25, to_ts)
    vn30 = index_move(vn30_bars, "VN30") if vn30_bars is not None else None
    live = move.session_date == now.date()

    watched = sorted({s.upper() for s in watched})
    universe = _breadth_universe()
    board_symbols = sorted(set(universe) | set(watched))
    quotes = quotes_from_board(fetch_price_board(board_symbols)) if live else pd.DataFrame()
    if not live:
        quotes = _quotes_from_store(board_symbols, move.session_date)

    breadth = compute_breadth(quotes[quotes["symbol"].isin(universe)]) if not quotes.empty else None

    index_close = _close_by_date(index_bars)
    index_close = index_close[index_close.index.date < move.session_date]
    history = _stock_history(watched)
    by_symbol = quotes.set_index("symbol") if not quotes.empty else pd.DataFrame()

    impacts: dict[str, SymbolImpact] = {}
    missing: list[str] = []
    for sym in watched:
        if sym not in by_symbol.index:
            missing.append(sym)
            continue
        row = by_symbol.loc[sym]
        closes = history.get(sym, _EMPTY_CLOSES)
        closes = closes[closes.index.date < move.session_date]
        beta, corr = beta_vs_index(closes, index_close)
        market_part, own_part = decompose(float(row["change_pct"]), beta, move.change_pct)
        net = row.get("foreign_net_value")
        impacts[sym] = SymbolImpact(
            symbol=sym,
            price=float(row["price"]),
            change_pct=float(row["change_pct"]),
            beta=beta,
            correlation=corr,
            market_part=market_part,
            own_part=own_part,
            foreign_net_value=None if pd.isna(net) else float(net),
        )
    return MarketPulse(
        as_of=now, live=live, index=move, vn30=vn30, breadth=breadth,
        impacts=impacts, missing=missing,
    )


def _quotes_from_store(symbols: list[str], session_date: date) -> pd.DataFrame:
    """Ngoai gio giao dich (chua co nen hom nay): bien dong cua phien
    `session_date` tinh tu kho gia (2 nen cuoi), khong co so lieu khoi ngoai."""
    stored = market_store.load_ohlcv(symbols, columns=["symbol", "time", "close"])
    rows = []
    for sym, group in stored.groupby("symbol", observed=True):
        closes = _close_by_date(group)
        closes = closes[closes.index.date <= session_date]
        if len(closes) < 2 or closes.index[-1].date() != session_date:
            continue
        prev, last = float(closes.iloc[-2]), float(closes.iloc[-1])
        if prev > 0:
            rows.append({"symbol": str(sym), "price": last, "ref_price": prev,
                         "change_pct": last / prev - 1, "foreign_net_value": float("nan")})
    return pd.DataFrame(rows, columns=["symbol", "price", "ref_price", "change_pct",
                                       "foreign_net_value"])
