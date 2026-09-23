import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from bot_phan_tich.analysis import snapshot as snapshot_mod
from bot_phan_tich.config import Paths
from bot_phan_tich.data import fundamentals_store, market_store

VN = ZoneInfo("Asia/Ho_Chi_Minh")


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    for mod in (market_store, snapshot_mod, fundamentals_store):
        monkeypatch.setattr(mod, "get_paths", lambda: paths)
    market_store._cache.clear()
    fundamentals_store._cache.clear()
    return paths


def _random_walk(symbol: str, bars: int = 150, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 20_000 + np.cumsum(rng.normal(0, 200, bars))
    return pd.DataFrame(
        {
            "symbol": symbol,
            "time": pd.bdate_range("2024-01-01", periods=bars),
            "open": close, "high": close + 150, "low": close - 150, "close": close,
            "volume": rng.integers(200_000, 900_000, bars).astype(float),
        }
    )


def _seed_store(symbols: dict[str, int]) -> None:
    frames = [_random_walk(s, bars, seed=i) for i, (s, bars) in enumerate(symbols.items())]
    market_store.save_ohlcv(pd.concat(frames, ignore_index=True), merge=False)


def test_build_snapshot_reads_store_once_and_skips_short_history(isolated_paths, monkeypatch):
    _seed_store({"AAA": 150, "BBB": 150, "SHORT": 30})

    calls = []
    real_load = market_store.load_ohlcv

    def spy_load(*args, **kwargs):
        calls.append((args, kwargs))
        return real_load(*args, **kwargs)

    monkeypatch.setattr(market_store, "load_ohlcv", spy_load)

    frame = snapshot_mod.build_snapshot(["AAA", "BBB", "SHORT"])

    assert len(calls) == 1  # doc kho DUNG MOT LAN, khong doc lai cho tung ma
    assert set(frame["symbol"]) == {"AAA", "BBB"}  # SHORT < 60 phien -> bo qua
    assert snapshot_mod.snapshot_path().exists()


def test_build_snapshot_thread_pool_gives_same_rows(isolated_paths):
    _seed_store({"AAA": 150, "BBB": 150, "CCC": 150})

    sequential = snapshot_mod.build_snapshot(["AAA", "BBB", "CCC"], max_workers=1)
    threaded = snapshot_mod.build_snapshot(["AAA", "BBB", "CCC"], max_workers=3)

    cols = ["symbol", "action", "total_score"]
    pd.testing.assert_frame_equal(
        sequential[cols].sort_values("symbol").reset_index(drop=True),
        threaded[cols].sort_values("symbol").reset_index(drop=True),
    )


def test_build_snapshot_missing_symbol_is_skipped_not_crash(isolated_paths):
    _seed_store({"AAA": 150})
    frame = snapshot_mod.build_snapshot(["AAA", "NOT_IN_STORE"])
    assert list(frame["symbol"]) == ["AAA"]


# ------------------------------------------------------------------ mui gio
def _write_snapshot_at(vn_time: datetime) -> None:
    """Tao file snapshot co mtime dung bang thoi diem `vn_time` (gio VN)."""
    path = snapshot_mod.snapshot_path()
    pd.DataFrame({"symbol": ["AAA"]}).to_parquet(path, index=False)
    ts = vn_time.timestamp()
    os.utime(path, (ts, ts))


def _utc_server_clock(monkeypatch, utc_now: datetime) -> None:
    """Gia lap may chu chay UTC (nhu Render): datetime.now() KHONG kem mui gio
    tra ve gio UTC; datetime.now(tz) quy doi dung sang tz."""

    class UtcServerDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_now.astimezone(tz) if tz else utc_now.replace(tzinfo=None)

    monkeypatch.setattr(snapshot_mod, "datetime", UtcServerDatetime)


def test_snapshot_built_after_close_is_fresh_on_utc_server(isolated_paths, monkeypatch):
    """Yeu cau Phan 3: may chu UTC, gio VN 15:30 -> snapshot vua dung luc
    15:20 (gio VN) phai duoc coi la MOI."""
    _write_snapshot_at(datetime(2026, 9, 23, 15, 20, tzinfo=VN))  # thu Tu
    _utc_server_clock(monkeypatch, datetime(2026, 9, 23, 8, 30, tzinfo=timezone.utc))

    assert snapshot_mod.is_stale() is False
    assert snapshot_mod.last_expected_session() == date(2026, 9, 23)


def test_yesterday_snapshot_is_stale_after_todays_close_on_utc_server(
    isolated_paths, monkeypatch
):
    """Loi cu: 16:00 gio VN = 09:00 UTC < 15:10 -> ban cu tuong "chua dong
    cua", coi snapshot hom qua van moi suot 7 tieng. Gio phai la CU."""
    _write_snapshot_at(datetime(2026, 9, 23, 15, 20, tzinfo=VN))
    _utc_server_clock(monkeypatch, datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc))

    assert snapshot_mod.is_stale() is True


def test_before_close_expects_previous_session(isolated_paths):
    _write_snapshot_at(datetime(2026, 9, 23, 15, 20, tzinfo=VN))
    morning = datetime(2026, 9, 24, 1, 0, tzinfo=timezone.utc)  # 08:00 gio VN
    assert snapshot_mod.last_expected_session(morning) == date(2026, 9, 23)
    assert snapshot_mod.is_stale(morning) is False


def test_weekend_expects_friday_session():
    saturday = datetime(2026, 9, 26, 10, 0, tzinfo=VN)
    assert snapshot_mod.last_expected_session(saturday) == date(2026, 9, 25)


def test_snapshot_last_updated_is_timezone_aware(isolated_paths):
    _write_snapshot_at(datetime(2026, 9, 23, 15, 20, tzinfo=VN))
    updated = snapshot_mod.snapshot_last_updated()
    assert updated.utcoffset() is not None
    assert updated == datetime(2026, 9, 23, 15, 20, tzinfo=VN)


# ------------------------------------------------ trang thai tien trinh nen (Phan 4)
@pytest.fixture
def fresh_status(monkeypatch):
    status = snapshot_mod.BuildStatus()
    monkeypatch.setattr(snapshot_mod, "_status", status)
    return status


async def test_update_records_error_instead_of_swallowing(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    def broken_bootstrap(progress=None):
        raise ConnectionError("Vietcap timeout")

    monkeypatch.setattr(market_store, "bootstrap", broken_bootstrap)

    ran = await snapshot_mod.update_market_data(force=True)

    assert ran is True
    assert fresh_status.running is False
    assert fresh_status.finished_at is not None
    assert "ConnectionError: Vietcap timeout" in fresh_status.last_error
    message = snapshot_mod.data_unavailable_message()
    assert "thất bại" in message and "Vietcap timeout" in message and "/trangthai" in message


async def test_update_reports_empty_source_as_error(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    monkeypatch.setattr(market_store, "bootstrap", lambda progress=None: 0)

    await snapshot_mod.update_market_data(force=True)

    assert "rỗng" in fresh_status.last_error


async def test_update_success_builds_snapshot_and_reports_progress(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    seen_progress = []

    def fake_bootstrap(progress=None):
        _seed_store({"AAA": 300, "BBB": 300})
        progress(2, 2)
        seen_progress.append((fresh_status.step, fresh_status.done, fresh_status.total))
        return 600

    monkeypatch.setattr(market_store, "bootstrap", fake_bootstrap)

    await snapshot_mod.update_market_data(force=True)

    assert seen_progress == [(snapshot_mod.STEP_BOOTSTRAP, 2, 2)]
    assert fresh_status.last_error is None
    assert fresh_status.last_result == "2 mã"
    assert set(snapshot_mod.load_snapshot()["symbol"]) == {"AAA", "BBB"}


async def test_concurrent_updates_do_not_overlap(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    """Luong khoi dong va lich 15h05 cung ghi mot file parquet - khong duoc chay chong."""
    import asyncio
    import threading
    import time

    active = 0
    max_active = 0
    lock = threading.Lock()

    def slow_bootstrap(progress=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.2)
        with lock:
            active -= 1
        return 0

    monkeypatch.setattr(market_store, "bootstrap", slow_bootstrap)

    await asyncio.gather(
        snapshot_mod.update_market_data(force=True),
        snapshot_mod.update_market_data(force=True),
    )

    assert max_active == 1


def test_progress_text_shows_counts_and_eta(fresh_status):
    fresh_status.running = True
    fresh_status.step = snapshot_mod.STEP_BOOTSTRAP
    fresh_status.done, fresh_status.total = 450, 1500
    fresh_status.step_started_at = datetime.now(VN) - timedelta(seconds=60)

    text = snapshot_mod.progress_text()

    assert text.startswith("Đang nạp kho giá toàn sàn: 450/1500 mã")
    assert "khoảng 2 phút nữa" in text  # 60s cho 450 ma -> con ~140s
    assert "450/1500" in snapshot_mod.data_unavailable_message()


def test_data_unavailable_message_when_never_ran(fresh_status):
    message = snapshot_mod.data_unavailable_message()
    assert "Chưa có dữ liệu" in message and "/trangthai" in message


# ------------------------------------------ du lieu toi thieu khi kho rong (Phan 5)
@pytest.fixture
def fake_watchlist_source(monkeypatch):
    """Nguon gia gia lap: danh sach theo doi AAA, BBB; tai tuc thi."""
    from bot_phan_tich.data import vietcap as vietcap_mod

    monkeypatch.setattr(snapshot_mod, "get_universe_config", lambda: {"watchlist": ["aaa", "bbb"]})
    monkeypatch.setattr(
        vietcap_mod, "fetch_all_symbols",
        lambda exchanges: pd.DataFrame(
            {"symbol": ["AAA", "BBB", "CCC"], "exchange": ["HOSE", "HNX", "HOSE"]}
        ),
    )
    monkeypatch.setattr(
        vietcap_mod, "fetch_ohlcv_bulk",
        lambda symbols, count_back, progress=None: pd.concat(
            [_random_walk(s, 300, seed=i) for i, s in enumerate(symbols)], ignore_index=True
        ),
    )


async def test_empty_store_serves_watchlist_snapshot_before_full_bootstrap(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    from bot_phan_tich.analysis import screener

    seen_during_bootstrap = {}

    def slow_full_bootstrap(progress=None):
        # Trong luc nap toan san: /loc PHAI co ket qua that tu ban tam.
        report = screener.screen_report(screener.ScreenCriteria())
        seen_during_bootstrap["symbols"] = {r.symbol for r in report.results}
        seen_during_bootstrap["note"] = report.note
        seen_during_bootstrap["store_empty"] = market_store.load_ohlcv().empty
        _seed_store({"AAA": 300, "BBB": 300, "CCC": 300})
        return 900

    monkeypatch.setattr(market_store, "bootstrap", slow_full_bootstrap)

    await snapshot_mod.update_market_data(force=False)

    assert seen_during_bootstrap["symbols"] == {"AAA", "BBB"}
    assert "Dữ liệu tạm thời: 2 mã" in seen_during_bootstrap["note"]
    # ban tam KHONG duoc ghi vao kho - kho chi xuat hien khi du ca san
    assert seen_during_bootstrap["store_empty"] is True
    # xong toan san: snapshot day du thay the ban tam
    assert snapshot_mod.is_partial_snapshot() is False
    assert set(snapshot_mod.load_snapshot()["symbol"]) == {"AAA", "BBB", "CCC"}


async def test_failed_bootstrap_keeps_watchlist_results_with_error_note(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    from bot_phan_tich.analysis import screener

    def broken_bootstrap(progress=None):
        raise ConnectionError("Vietcap chan IP")

    monkeypatch.setattr(market_store, "bootstrap", broken_bootstrap)

    await snapshot_mod.update_market_data(force=False)

    report = screener.screen_report(screener.ScreenCriteria())
    assert {r.symbol for r in report.results} == {"AAA", "BBB"}  # khong bao gio trong tron
    assert snapshot_mod.is_partial_snapshot() is True
    assert "Vietcap chan IP" in report.note


async def test_partial_snapshot_triggers_update_even_if_fresh(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    """Snapshot tam vua dung (con "moi") nhung chua du toan san -> lan khoi
    dong sau van phai nap toan san, khong duoc bo qua vi is_stale() = False."""
    snapshot_mod.build_quick_snapshot()
    calls = []
    monkeypatch.setattr(market_store, "bootstrap", lambda progress=None: calls.append(1) or 0)

    ran = await snapshot_mod.update_market_data(force=False)

    assert ran is True and calls == [1]


async def test_quick_snapshot_does_not_replace_full_snapshot(
    isolated_paths, fresh_status, fake_watchlist_source, monkeypatch
):
    _seed_store({"AAA": 300, "BBB": 300, "CCC": 300})
    snapshot_mod.build_snapshot(["AAA", "BBB", "CCC"])
    market_store.ohlcv_path().unlink()  # kho mat, snapshot day du van con
    market_store._cache.clear()
    monkeypatch.setattr(market_store, "bootstrap", lambda progress=None: 0)

    await snapshot_mod.update_market_data(force=False)

    assert set(snapshot_mod.load_snapshot()["symbol"]) == {"AAA", "BBB", "CCC"}
    assert snapshot_mod.is_partial_snapshot() is False
