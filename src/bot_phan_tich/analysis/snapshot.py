"""Tinh san khuyen nghi CUOI NGAY cho toan bo vu tru thanh khoan.

Giai quyet van de: chi bao ky thuat theo ngay KHONG DOI trong pham vi mot
phien, nen /loc va /tinhieu khong can tinh lai moi lan nguoi dung bam nut -
chi can TRA BANG mot snapshot da tinh san MOT LAN sau gio dong cua.

build_snapshot() goi analysis.scoring.recommend() DUNG MOT LAN cho moi ma -
recommend() da tu tinh macd_state/rsi_state/ichimoku_state/divergence/
volume_ratio va tra kem theo trong Recommendation, KHONG tinh lai o day
(xem analysis/scoring.py).

Doc kho DUNG MOT LAN o tien trinh chinh (market_store.frames_by_symbol), roi
duyet TUAN TU. Khong dung da tien trinh: ban cu dung ProcessPoolExecutor voi
max(1, os.cpu_count() - 1) tien trinh con, MOI tien trinh tu doc lai TOAN BO
kho (~111 MB) - tren container, os.cpu_count() tra so core may chu vat ly
(khong phai han muc CPU duoc cap), nen de dang vuot 512 MB cua Render goi
Free -> OOM kill -> mat dia tam -> nap lai -> lap vo tan. Do thuc te
recommend() chi mat ~15 ms/ma, 700 ma ~ 11 giay tren MOT luong - da tien
trinh khong dang voi chi phi RAM. Van cho phep ThreadPoolExecutor qua
config `snapshot.max_workers` (mac dinh 1).
"""
from __future__ import annotations

import asyncio
import time as time_module
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from datetime import time as dt_time

import pandas as pd

from ..config import bot_timezone, get_paths, get_settings, get_universe_config
from ..data import fundamentals_store, market_store
from ..data.universe import liquid_universe
from ..logging_conf import get_logger
from ..sysinfo import format_mb, peak_rss_mb
from .scoring import recommend

log = get_logger(__name__)

SNAPSHOT_FILENAME = "snapshot.parquet"
_MIN_BARS = 60
_MARKET_CLOSE_CUTOFF = dt_time(15, 10)  # trung voi bot.scan_cron mac dinh
_PROGRESS_EVERY = 200


def snapshot_path():
    d = get_paths().data_dir / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d / SNAPSHOT_FILENAME


def _evaluate_one(symbol: str, exchange: str | None, frame: pd.DataFrame) -> dict | None:
    """Tinh mot dong snapshot tu DataFrame gia CUA RIENG ma nay (da doc san o
    build_snapshot, khong tu doc lai kho). Tra None neu thieu du lieu hoac
    loi - khong lam hong ca lot tinh.
    """
    if len(frame) < _MIN_BARS:
        return None
    try:
        rec = recommend(frame, symbol)
    except Exception as exc:  # noqa: BLE001 - ghi log, bo qua ma nay, khong lan ca lot
        log.warning("build_snapshot: bo qua %s do loi: %s", symbol, exc)
        return None

    close_series = frame["close"]
    prev_close = float(close_series.iloc[-2]) if len(close_series) > 1 else rec.close
    change_pct = (rec.close / prev_close - 1) if prev_close else None

    macd_st, rsi_st, ichi_st = rec.macd_state, rec.rsi_state, rec.ichimoku_state
    tk_cross = ichi_st.get("tk_cross") or (None, None, None)

    return {
        "symbol": symbol,
        "exchange": exchange,
        "close": rec.close,
        "change_pct": change_pct,
        "volume": float(frame["volume"].iloc[-1]),
        "vol_ratio20": rec.volume_ratio,
        "action": rec.action,
        "total_score": rec.total_score,
        "score_macd": rec.component_scores.get("macd"),
        "score_rsi": rec.component_scores.get("rsi"),
        "score_ichimoku": rec.component_scores.get("ichimoku"),
        "price_vs_kumo": ichi_st.get("price_vs_kumo"),
        "kumo_break_bars": ichi_st.get("kumo_break_bars"),
        "kumo_thickness": ichi_st.get("kumo_thickness"),
        "macd_cross": macd_st.get("cross"),
        "macd_bars_since": macd_st.get("bars_since_cross"),
        "macd_above_zero": macd_st.get("above_zero"),
        "rsi": rsi_st.get("value"),
        "rsi_zone": rsi_st.get("zone"),
        "rsi_upper": rsi_st.get("upper"),
        "rsi_lower": rsi_st.get("lower"),
        "divergence_type": rec.divergence.get("type"),
        "tk_cross": tk_cross[0],
        "stop_loss": rec.stop_loss,
        "target": rec.target,
        "reasons": list(rec.reasons),
        "as_of": frame["time"].iloc[-1],
    }


def _safe_evaluate(task: tuple[str, str | None, pd.DataFrame | None]) -> dict | None:
    symbol, exchange, frame = task
    if frame is None:
        return None
    try:
        return _evaluate_one(symbol, exchange, frame)
    except Exception as exc:  # noqa: BLE001 - mot ma loi khong duoc lam hong ca lot
        log.warning("build_snapshot: bo qua %s do loi: %s", symbol, exc)
        return None


def build_snapshot(
    symbols: list[str] | None = None,
    max_workers: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Tinh khuyen nghi cho toan bo `symbols` (mac dinh: liquid_universe()),
    ghi ra snapshot.parquet. Tra ve chinh DataFrame vua ghi.

    Doc kho MOT LAN (frames_by_symbol), duyet tuan tu - RAM them toi da ~mot
    ban sao kho gia (cac DataFrame theo tung ma). `max_workers` > 1 (hoac
    config `snapshot.max_workers`) thi dung ThreadPoolExecutor, van chung
    mot tien trinh, khong nhan ban kho.
    """
    if symbols is None:
        # Nap ca kho vao cache TRUOC: liquid_universe() va frames_by_symbol()
        # ben duoi deu lay tu cache nay - file kho chi doc DUNG MOT LAN.
        market_store.load_ohlcv()
        symbols = liquid_universe()
    if not symbols:
        log.warning("build_snapshot: vu tru rong (chua backfill?), khong tinh gi")
        return pd.DataFrame()

    symbols_meta = market_store.load_symbols()
    exchange_map: dict[str, str] = {}
    if not symbols_meta.empty and "exchange" in symbols_meta.columns:
        exchange_map = dict(zip(symbols_meta["symbol"], symbols_meta["exchange"], strict=False))

    frames = market_store.frames_by_symbol(symbols)
    tasks = [(s, exchange_map.get(s), frames.get(s)) for s in symbols]
    workers = max_workers or int(get_settings().get("snapshot.max_workers", 1))

    started = time_module.time()
    rows = _compute_rows(tasks, workers, progress)
    elapsed = time_module.time() - started
    log.info(
        "build_snapshot: %d/%d ma thanh cong trong %.1fs", len(rows), len(symbols), elapsed
    )
    return _write_snapshot(rows, partial=False)


def _compute_rows(
    tasks: list[tuple[str, str | None, pd.DataFrame | None]],
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    failed = 0
    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    results = executor.map(_safe_evaluate, tasks) if executor else map(_safe_evaluate, tasks)
    try:
        for done, row in enumerate(results, start=1):
            if row is not None:
                rows.append(row)
            else:
                failed += 1
            if progress is not None:
                progress(done, len(tasks))
            if done % _PROGRESS_EVERY == 0 or done == len(tasks):
                log.info(
                    "build_snapshot: %d/%d ma (%d bi bo qua), RAM dinh %s",
                    done, len(tasks), failed, format_mb(peak_rss_mb()),
                )
    finally:
        if executor is not None:
            executor.shutdown()
    return rows


def _partial_marker_path():
    return snapshot_path().with_name("snapshot.partial")


def is_partial_snapshot() -> bool:
    """True neu snapshot hien tai chi la ban TAM (danh sach theo doi), chua
    phai toan san - xem build_quick_snapshot(). Danh dau bang file rieng de
    con dung sau khi bot khoi dong lai."""
    return _partial_marker_path().exists()


def _write_snapshot(rows: list[dict], partial: bool) -> pd.DataFrame:
    frame = _merge_fundamentals(pd.DataFrame(rows))
    frame.to_parquet(snapshot_path(), index=False)
    marker = _partial_marker_path()
    if partial:
        marker.touch()
    else:
        marker.unlink(missing_ok=True)
    return frame


def build_quick_snapshot(progress: Callable[[int, int], None] | None = None) -> pd.DataFrame:
    """Dung snapshot TAM cho danh sach theo doi trong config/universe.yaml (~12
    ma, vai giay) khi kho gia con rong - de /loc, /tinhieu co ket qua THAT
    ngay sau khi bot khoi dong tren may trang du lieu (vd Render goi Free sau
    moi lan restart), trong luc market_store.bootstrap() nap toan san o nen.

    Chi ghi snapshot (danh dau la ban tam), KHONG ghi vao kho gia: kho chi
    xuat hien khi da du ca san (xem bootstrap()), neu khong lan sau bot se
    tuong "da co kho" va khong nap toan san nua.
    """
    from ..data.vietcap import fetch_all_symbols, fetch_ohlcv_bulk  # tranh import vong

    settings = get_settings()
    symbols = [s.upper() for s in get_universe_config()["watchlist"]]

    exchange_map: dict[str, str] = {}
    try:
        listing = fetch_all_symbols(settings.get("universe.exchanges", ["HOSE", "HNX", "UPCOM"]))
        if not listing.empty:
            market_store.save_symbols(listing)
            exchange_map = dict(zip(listing["symbol"], listing["exchange"], strict=False))
    except Exception as exc:  # noqa: BLE001 - thieu ten san van dung duoc snapshot tam
        log.warning("build_quick_snapshot: khong lay duoc danh sach san: %s", exc)

    count_back = int(settings.get("market_store.count_back_bootstrap", 500))
    raw = fetch_ohlcv_bulk(symbols, count_back=count_back, progress=progress)
    if raw.empty:
        return pd.DataFrame()
    frames = {
        str(s): g.sort_values("time").reset_index(drop=True)
        for s, g in raw.groupby("symbol", sort=False)
    }
    rows = _compute_rows([(s, exchange_map.get(s), frames.get(s)) for s in symbols])
    if not rows:
        return pd.DataFrame()
    log.info("build_quick_snapshot: snapshot tam %d ma", len(rows))
    return _write_snapshot(rows, partial=True)


def _merge_fundamentals(frame: pd.DataFrame) -> pd.DataFrame:
    """Gop cot pe/pb/roe tu data/fundamentals_store.py neu kho da co (chay
    scripts/backfill_fundamentals.py truoc). Ma nao khong co trong kho fundamentals
    (chua backfill, hoac nguon khong tra duoc) se la NaN - screener.py tu bo qua
    dieu kien loc theo fundamentals cho ma do, KHONG bia so."""
    fundamentals = fundamentals_store.load_fundamentals()
    if fundamentals.empty:
        return frame
    return frame.merge(
        fundamentals[["symbol", "pe", "pb", "roe"]], on="symbol", how="left"
    )


def load_snapshot() -> pd.DataFrame:
    path = snapshot_path()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def snapshot_last_updated() -> datetime | None:
    """Thoi diem ghi snapshot, CO gan mui gio bot.timezone (khong phu thuoc
    mui gio cua may chu)."""
    path = snapshot_path()
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=bot_timezone())


def _as_local(now: datetime | None) -> datetime:
    """Quy `now` ve gio bot.timezone. Gio khong gan mui gio duoc coi la DA la
    gio dia phuong cua bot (khong phai gio may chu)."""
    tz = bot_timezone()
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def last_expected_session(now: datetime | None = None) -> date:
    """Ngay lam viec gan nhat MA snapshot LE RA phai co du lieu, tinh tu
    `now`. Xap xi don gian (khong tinh ngay le) dua tren gio dong cua
    `_MARKET_CLOSE_CUTOFF` va cuoi tuan - du dung de canh bao "du lieu cu",
    khong doi hoi chinh xac tuyet doi.

    Tinh theo gio bot.timezone (Viet Nam), KHONG theo gio may chu: Render
    chay UTC, lech 7 gio - neu dung datetime.now() tran thi 15h30 gio VN
    (08h30 UTC) bi coi la "truoc gio dong cua".
    """
    now = _as_local(now)
    d = now.date()
    if now.weekday() >= 5 or now.time() < _MARKET_CLOSE_CUTOFF:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def is_stale(now: datetime | None = None) -> bool:
    """True neu chua co snapshot, hoac snapshot cu hon phien giao dich gan nhat."""
    updated = snapshot_last_updated()
    if updated is None:
        return True
    return updated.date() < last_expected_session(now)


# ------------------------------------------- cap nhat du lieu o nen + trang thai
STEP_QUICK = "Đang nạp dữ liệu tạm cho danh sách theo dõi"
STEP_BOOTSTRAP = "Đang nạp kho giá toàn sàn"
STEP_REFRESH = "Đang cập nhật kho giá"
STEP_SNAPSHOT = "Đang tính khuyến nghị toàn sàn"
_ERROR_MAX_CHARS = 200


@dataclass
class BuildStatus:
    """Trang thai tien trinh cap nhat du lieu o nen. Hien trong /trangthai va
    trong thong bao cua /loc, /tinhieu khi chua co du lieu - de nguoi dung
    thay DANG LAM GI, DEN DAU va LOI GI, thay vi mot cau "dang chuan bi"."""

    running: bool = False
    step: str | None = None
    done: int = 0
    total: int = 0
    started_at: datetime | None = None
    step_started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    last_result: str | None = None

    def eta_seconds(self) -> float | None:
        """Uoc tinh thoi gian con lai cua buoc hien tai, theo toc do tu dau buoc."""
        if not self.running or self.done <= 0 or self.total <= 0 or not self.step_started_at:
            return None
        elapsed = (_as_local(None) - self.step_started_at).total_seconds()
        return elapsed / self.done * (self.total - self.done)


_status = BuildStatus()
_pipeline_lock = asyncio.Lock()


def get_build_status() -> BuildStatus:
    """Ban sao trang thai hien tai (khong de noi goi sua nham trang thai that)."""
    return replace(_status)


def is_build_in_progress() -> bool:
    return _status.running


def _begin_step(step: str) -> None:
    _status.step = step
    _status.done = 0
    _status.total = 0
    _status.step_started_at = _as_local(None)
    log.info("cap nhat du lieu: %s", step)


def _report_progress(done: int, total: int) -> None:
    _status.done = done
    _status.total = total


def _short_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= _ERROR_MAX_CHARS else text[: _ERROR_MAX_CHARS - 1] + "…"


def _humanize_seconds(seconds: float) -> str:
    return "dưới 1 phút" if seconds < 60 else f"{round(seconds / 60)} phút"


def progress_text() -> str | None:
    """Vd "Đang nạp kho giá toàn sàn: 450/1500 mã (khoảng 2 phút nữa)".
    None neu khong co tien trinh nao dang chay."""
    status = _status
    if not status.running or not status.step:
        return None
    text = status.step
    if status.total:
        text += f": {status.done}/{status.total} mã"
    eta = status.eta_seconds()
    if eta is not None:
        text += f" (khoảng {_humanize_seconds(eta)} nữa)"
    return text


def data_unavailable_message() -> str:
    """Giai thich VI SAO chua co du lieu cho /loc, /tinhieu - dang lam den
    dau, hay lan truoc that bai vi loi gi. Van ban THO (chua escape HTML)."""
    running = progress_text()
    if running:
        return f"⏳ {running}. Vui lòng thử lại sau ít phút. Gõ /trangthai để xem chi tiết."
    if _status.last_error:
        return (
            f"⚠️ Lần dựng dữ liệu gần nhất thất bại: {_status.last_error}. "
            "Gõ /trangthai để xem chi tiết."
        )
    return (
        "Chưa có dữ liệu khuyến nghị. Bot tự nạp dữ liệu khi khởi động và sau "
        "mỗi phiên (hoặc chạy scripts/backfill_data.py rồi scripts/build_snapshot.py). "
        "Gõ /trangthai để xem chi tiết."
    )


def _store_is_empty() -> bool:
    return market_store.load_ohlcv(columns=["symbol"]).empty


async def _build_quick_snapshot_if_needed() -> None:
    """Snapshot tam cho danh sach theo doi - chi khi chua co snapshot day du
    (khong ghi de mot snapshot toan san con dung duoc bang ban 12 ma). Loi o
    buoc nay chi ghi log: buoc nap toan san ngay sau van chay va se ghi loi
    vao trang thai neu nguon du lieu that su hong."""
    has_full = not is_partial_snapshot() and not (await asyncio.to_thread(load_snapshot)).empty
    if has_full:
        return
    _begin_step(STEP_QUICK)
    try:
        frame = await asyncio.to_thread(build_quick_snapshot, progress=_report_progress)
        log.info("update_market_data: snapshot tam %d ma", len(frame))
    except Exception as exc:  # noqa: BLE001
        log.warning("update_market_data: snapshot tam that bai: %s", exc)


async def update_market_data(force: bool = False) -> bool:
    """Cap nhat kho gia roi dung lai snapshot - MOT luong duy nhat cho ca luc
    khoi dong (ensure_fresh_in_background) va lich quet cuoi phien
    (bot/main.py:daily_scan_job). Khoa `_pipeline_lock` dam bao hai luong
    khong chay chong len nhau (cung ghi mot file parquet). Moi buoc nang
    chay trong thread rieng (asyncio.to_thread), khong chan event loop.

    Kho HOAN TOAN RONG (vd container Render goi Free khong co dia luu ben
    vung, moi lan restart la mat sach data/) can market_store.bootstrap()
    (nap toan bo) thay vi refresh() (chi tai bu cho ma DA CO, tren kho rong
    khong lam gi ca).

    Kho rong va chua co snapshot day du: TRUOC TIEN dung snapshot tam cho
    danh sach theo doi (vai giay, build_quick_snapshot) de /loc, /tinhieu co
    ket qua ngay - roi moi nap toan san (vai phut) va dung snapshot day du.

    `force=False`: bo qua neu kho da co, snapshot con moi va khong phai ban
    tam. Cap nhat _status o MOI buoc, ke ca khi loi - loi duoc giu lai de hien
    cho nguoi dung. Tra ve True neu da thuc su chay.
    """
    async with _pipeline_lock:
        store_empty = await asyncio.to_thread(_store_is_empty)
        if not force and not store_empty and not is_stale() and not is_partial_snapshot():
            return False

        _status.running = True
        _status.started_at = _as_local(None)
        _status.finished_at = None
        _status.last_error = None
        try:
            if store_empty:
                await _build_quick_snapshot_if_needed()
                _begin_step(STEP_BOOTSTRAP)
                rows = await asyncio.to_thread(market_store.bootstrap, progress=_report_progress)
                if rows == 0:
                    _status.last_error = (
                        "Không tải được dữ liệu giá (nguồn Vietcap trả về rỗng — có thể "
                        "đang bị giới hạn tần suất hoặc chặn IP). Sẽ thử lại lần quét sau."
                    )
                    return True
            else:
                _begin_step(STEP_REFRESH)
                await asyncio.to_thread(market_store.refresh, progress=_report_progress)

            _begin_step(STEP_SNAPSHOT)
            frame = await asyncio.to_thread(build_snapshot, progress=_report_progress)
            _status.last_result = f"{len(frame)} mã"
            if frame.empty:
                _status.last_error = (
                    "Kho giá đã có nhưng không mã nào đủ điều kiện thanh khoản — "
                    "kiểm tra dữ liệu hoặc ngưỡng universe.* trong config."
                )
        except Exception as exc:  # noqa: BLE001 - loi phai HIEN cho nguoi dung, khong nuot
            log.exception("update_market_data: that bai")
            _status.last_error = _short_error(exc)
        finally:
            _status.running = False
            _status.step = None
            _status.finished_at = _as_local(None)
        return True


async def ensure_fresh_in_background() -> None:
    """Goi tu bot/main.py nhu task nen luc khoi dong: neu snapshot thieu/cu thi
    cap nhat (xem update_market_data) - KHONG chan bot khoi dong."""
    await update_market_data(force=False)
