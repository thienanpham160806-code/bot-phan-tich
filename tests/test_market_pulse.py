"""Kiem thu ban tin bien dong thi truong (/biendong) - khong goi mang."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from bot_phan_tich.analysis import market_pulse as mp
from bot_phan_tich.bot.formatters import market_pulse_card
from bot_phan_tich.config import Paths, auto_subscribe_chat_ids
from bot_phan_tich.data import cache
from bot_phan_tich.data.cache import (
    get_news_subscribers,
    get_pulse_subscribers,
    init_db,
    set_news_subscriber,
    set_pulse_subscriber,
)

VN = timezone(timedelta(hours=7))


def _daily_index(n: int, end: str = "2026-09-23") -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


# ------------------------------------------------------------------ tinh toan
def test_beta_recovers_known_sensitivity():
    rng = np.random.default_rng(0)
    idx_ret = rng.normal(0, 0.01, 150)
    dates = _daily_index(151)
    index_close = pd.Series(1000 * np.cumprod(np.r_[1, 1 + idx_ret]), index=dates)
    stock_close = pd.Series(50 * np.cumprod(np.r_[1, 1 + 1.5 * idx_ret]), index=dates)

    beta, corr = mp.beta_vs_index(stock_close, index_close)
    assert beta == pytest.approx(1.5, rel=1e-6)
    assert corr == pytest.approx(1.0, rel=1e-6)


def test_beta_needs_enough_history():
    dates = _daily_index(20)
    series = pd.Series(np.linspace(10, 12, 20), index=dates)
    assert mp.beta_vs_index(series, series) == (None, None)


def test_daily_returns_drop_split_like_jumps():
    close = pd.Series([100, 101, 50.5, 51], index=_daily_index(4))  # chia tach 1:2
    returns = mp.daily_returns(close)
    assert len(returns) == 2
    assert (returns.abs() <= mp.MAX_ABS_DAILY_RETURN).all()


def test_decompose_and_verdict():
    market, own = mp.decompose(-0.012, 0.8, -0.01)
    assert market == pytest.approx(-0.008)
    assert own == pytest.approx(-0.004)

    def verdict(own_part, corr=0.6):
        return mp.SymbolImpact("X", 1, 0, beta=1, correlation=corr,
                               market_part=0, own_part=own_part).verdict

    assert verdict(0.01) == "mạnh hơn thị trường"
    assert verdict(-0.01) == "yếu hơn thị trường"
    assert verdict(0.001) == "đi cùng thị trường"
    assert "tương quan thấp" in verdict(0.02, corr=0.1)
    assert "chưa đủ lịch sử" in mp.SymbolImpact("X", 1, 0).verdict


def test_quotes_from_board_and_breadth():
    board = pd.DataFrame({
        "listingInfo.symbol": ["AAA", "BBB", "CCC", "DDD"],
        "matchPrice.matchPrice": [11000, 9000, 20000, 0],  # DDD chua khop lenh
        "matchPrice.referencePrice": [10000, 10000, 20000, 5000],
        "matchPrice.foreignBuyValue": [5e9, 0, 1e9, 0],
        "matchPrice.foreignSellValue": [1e9, 2e9, 1e9, 0],
    })
    quotes = mp.quotes_from_board(board)
    assert list(quotes["symbol"]) == ["AAA", "BBB", "CCC"]
    assert quotes.set_index("symbol").loc["AAA", "change_pct"] == pytest.approx(0.10)

    breadth = mp.compute_breadth(quotes)
    assert (breadth.advancers, breadth.decliners, breadth.unchanged) == (1, 1, 1)
    assert breadth.top_gainers == [("AAA", pytest.approx(0.10))]
    assert breadth.top_losers == [("BBB", pytest.approx(-0.10))]
    assert breadth.foreign_net_value == pytest.approx(2e9)


def test_index_move_uses_last_two_bars():
    bars = pd.DataFrame({
        "time": _daily_index(22), "open": 1.0, "high": 1810.0, "low": 1790.0,
        "close": [1800.0] * 21 + [1782.0], "volume": [100.0] * 21 + [50.0],
    })
    move = mp.index_move(bars, "VNINDEX")
    assert move.change_pts == pytest.approx(-18.0)
    assert move.change_pct == pytest.approx(-0.01)
    assert move.avg_volume_20 == pytest.approx(100.0)


# ------------------------------------------------------ build_market_pulse
@pytest.fixture
def fake_market(monkeypatch):
    """Gia lap Vietcap + kho gia: VNINDEX giam 1% hom nay, FPT beta 2."""
    from bot_phan_tich.analysis import snapshot
    from bot_phan_tich.data import vietcap

    rng = np.random.default_rng(1)
    idx_ret = rng.normal(0, 0.01, 150)
    dates = _daily_index(151, end="2026-09-23")
    index_hist = 1000 * np.cumprod(np.r_[1, 1 + idx_ret])
    fpt_hist = 50000 * np.cumprod(np.r_[1, 1 + 2 * idx_ret])
    state = {"today": pd.Timestamp("2026-09-24")}

    def fake_chart(symbol, count_back, to_ts):
        times = list(dates) + [state["today"]]
        closes = list(index_hist) + [index_hist[-1] * 0.99]
        return pd.DataFrame({"symbol": symbol, "time": times, "open": closes, "high": closes,
                             "low": closes, "close": closes, "volume": 1e6})

    def fake_board(symbols, **_):
        prices = {"FPT": fpt_hist[-1] * 0.97, "HPG": 21000.0}
        return pd.DataFrame({
            "listingInfo.symbol": list(prices),
            "matchPrice.matchPrice": list(prices.values()),
            "matchPrice.referencePrice": [fpt_hist[-1], 21000.0],
            "matchPrice.foreignBuyValue": [1e9, 0], "matchPrice.foreignSellValue": [3e9, 0],
        })

    stored = pd.DataFrame({"symbol": "FPT", "time": dates, "close": fpt_hist})
    monkeypatch.setattr(vietcap, "_fetch_ohlcv_one", fake_chart)
    monkeypatch.setattr(vietcap, "fetch_price_board", fake_board)
    monkeypatch.setattr(vietcap, "fetch_ohlcv_bulk",
                        lambda syms, **_: pd.DataFrame(columns=["symbol", "time", "close"]))
    monkeypatch.setattr(snapshot, "load_snapshot",
                        lambda: pd.DataFrame({"symbol": ["FPT", "HPG"]}))
    monkeypatch.setattr(mp.market_store, "load_ohlcv",
                        lambda symbols=None, since=None, columns=None:
                        stored[stored["symbol"].isin(symbols or [])])
    monkeypatch.setattr(mp, "now_local", lambda: datetime(2026, 9, 24, 11, 35, tzinfo=VN))
    return state


def test_build_market_pulse_live(fake_market):
    pulse = mp.build_market_pulse(["fpt", "HPG", "ZZZ"])
    assert pulse.live
    assert pulse.index.change_pct == pytest.approx(-0.01)
    assert pulse.missing == ["ZZZ"]

    fpt = pulse.impacts["FPT"]
    assert fpt.change_pct == pytest.approx(-0.03)
    assert fpt.beta == pytest.approx(2.0, rel=1e-6)
    assert fpt.market_part == pytest.approx(-0.02, rel=1e-6)
    assert fpt.own_part == pytest.approx(-0.01, rel=1e-6)
    assert fpt.verdict == "yếu hơn thị trường"
    assert fpt.foreign_net_value == pytest.approx(-2e9)
    assert pulse.impacts["HPG"].beta is None  # khong co lich su trong kho

    card = market_pulse_card(pulse, ["FPT", "HPG", "ZZZ"])
    assert "BIẾN ĐỘNG THỊ TRƯỜNG" in card and "hết phiên sáng" in card
    assert "Thị trường kéo -2.00%, riêng mã -1.00%" in card
    assert "bán ròng 2.0 tỷ đồng" in card
    assert "Chưa có giá trong phiên: ZZZ" in card


def test_build_market_pulse_holiday_is_not_live(fake_market, monkeypatch):
    # Ngay nghi: nen cuoi cua chi so la phien truoc, khong phai hom nay.
    monkeypatch.setattr(mp, "now_local", lambda: datetime(2026, 9, 25, 11, 35, tzinfo=VN))
    pulse = mp.build_market_pulse(["FPT"])
    assert not pulse.live
    assert "hôm nay chưa có giao dịch" in market_pulse_card(pulse, ["FPT"])


def test_card_stays_under_telegram_limit(fake_market):
    pulse = mp.build_market_pulse(["FPT"])
    impact = pulse.impacts["FPT"]
    many = [f"M{i:02d}" for i in range(40)]
    pulse.impacts = {s: impact for s in many}
    card = market_pulse_card(pulse, many, using_default=True)
    assert len(card) < 4096
    assert "25 mã khác" in card
    assert "danh sách mặc định" in card


# ----------------------------------------------------------- dang ky & job
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(cache, "get_paths", lambda: paths)
    init_db()
    return paths


def test_seed_subscribers_keeps_explicit_opt_out(isolated_db):
    set_news_subscriber(2, False)
    set_pulse_subscriber(2, False)
    cache.seed_subscribers([1, 2, -1001])
    assert sorted(get_news_subscribers()) == [-1001, 1]
    assert sorted(get_pulse_subscribers()) == [-1001, 1]


def test_auto_subscribe_chat_ids_parsing(monkeypatch):
    monkeypatch.setenv("AUTO_SUBSCRIBE_CHAT_IDS", " 123, -100456 ,abc,, 7")
    assert auto_subscribe_chat_ids() == [123, -100456, 7]


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **_):
        self.sent.append((chat_id, text))


def test_pulse_job_sends_only_on_trading_days(isolated_db, fake_market, monkeypatch):
    from bot_phan_tich.bot import main

    set_pulse_subscriber(42, True)
    bot = FakeBot()
    asyncio.run(main.market_pulse_job(bot))
    assert len(bot.sent) == 1 and bot.sent[0][0] == 42
    assert "danh sách mặc định" in bot.sent[0][1]  # chat 42 chua /sub ma nao

    monkeypatch.setattr(mp, "now_local", lambda: datetime(2026, 9, 25, 11, 35, tzinfo=VN))
    holiday_bot = FakeBot()
    asyncio.run(main.market_pulse_job(holiday_bot))
    assert holiday_bot.sent == []
