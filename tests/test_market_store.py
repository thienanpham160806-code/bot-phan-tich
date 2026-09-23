import pandas as pd
import pytest

from bot_phan_tich.config import Paths
from bot_phan_tich.data import market_store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Moi test dung mot thu muc data/ rieng, khong dung chung kho that."""
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(market_store, "get_paths", lambda: paths)
    market_store._cache.clear()
    return paths


def _frame(rows):
    return pd.DataFrame(rows, columns=market_store.OHLCV_COLUMNS)


def test_load_ohlcv_empty_when_no_store(isolated_store):
    assert market_store.load_ohlcv().empty
    assert market_store.last_updated() is None


def test_save_and_load_roundtrip(isolated_store):
    frame = _frame(
        [
            ["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000],
            ["fpt", "2024-01-02", 10.5, 11, 10, 10.8, 1200],
            ["vnm", "2024-01-01", 50, 51, 49, 50.5, 500],
        ]
    )
    total = market_store.save_ohlcv(frame, merge=False)
    assert total == 3

    loaded = market_store.load_ohlcv()
    assert len(loaded) == 3
    assert set(loaded["symbol"]) == {"FPT", "VNM"}

    fpt_only = market_store.load_ohlcv(["fpt"])
    assert len(fpt_only) == 2
    assert (fpt_only["symbol"] == "FPT").all()


def test_save_ohlcv_merges_and_deduplicates(isolated_store):
    first = _frame([["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000]])
    market_store.save_ohlcv(first, merge=False)

    # Ban ghi trung ngay 2024-01-01 (gia moi hon) + mot ngay moi.
    second = _frame(
        [
            ["fpt", "2024-01-01", 10, 11, 9, 10.9, 1000],  # cap nhat gia dong cua
            ["fpt", "2024-01-02", 10.9, 11.5, 10.5, 11.0, 1100],
        ]
    )
    total = market_store.save_ohlcv(second, merge=True)
    assert total == 2  # khong nhan doi ban ghi trung (symbol, time)

    loaded = market_store.load_ohlcv(["fpt"])
    row = loaded[loaded["time"] == pd.Timestamp("2024-01-01")].iloc[0]
    assert row["close"] == 10.9  # giu ban ghi MOI hon


def test_frames_by_symbol_groups_correctly(isolated_store):
    frame = _frame(
        [
            ["fpt", "2024-01-02", 10.5, 11, 10, 10.8, 1200],
            ["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000],
            ["vnm", "2024-01-01", 50, 51, 49, 50.5, 500],
        ]
    )
    market_store.save_ohlcv(frame, merge=False)

    grouped = market_store.frames_by_symbol()
    assert set(grouped) == {"FPT", "VNM"}
    assert list(grouped["FPT"]["time"]) == sorted(grouped["FPT"]["time"])  # sap xep tang dan


def test_cache_invalidates_when_file_changes(isolated_store):
    market_store.save_ohlcv(_frame([["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000]]), merge=False)
    first_load = market_store.load_ohlcv()
    assert len(first_load) == 1

    market_store.save_ohlcv(_frame([["vnm", "2024-01-01", 50, 51, 49, 50.5, 500]]), merge=True)
    second_load = market_store.load_ohlcv()
    assert len(second_load) == 2  # khong bi "dinh" du lieu cu tu lan doc truoc


def test_load_ohlcv_uses_memory_saving_dtypes(isolated_store):
    """Kho phai doc ra o dang tiet kiem RAM (category + float32) - can cho
    may chu 512 MB (Render goi Free)."""
    market_store.save_ohlcv(_frame([["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000]]), merge=False)
    loaded = market_store.load_ohlcv()
    assert str(loaded["symbol"].dtype) == "category"
    for col in ("open", "high", "low", "close", "volume"):
        assert str(loaded[col].dtype) == "float32"


def test_load_ohlcv_columns_subset_with_symbol_filter(isolated_store):
    market_store.save_ohlcv(
        _frame(
            [
                ["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000],
                ["vnm", "2024-01-01", 50, 51, 49, 50.5, 500],
            ]
        ),
        merge=False,
    )
    # Loc theo symbol du `columns` khong co "symbol" - ham tu doc them cot can loc.
    loaded = market_store.load_ohlcv(["vnm"], columns=["close"])
    assert list(loaded.columns) == ["close"]
    assert loaded["close"].tolist() == [50.5]


def test_frames_by_symbol_has_no_empty_groups_after_filter(isolated_store):
    """symbol la category - groupby phai dung observed=True, neu khong se
    sinh ra nhom RONG cho moi ma da bi loc bo."""
    market_store.save_ohlcv(
        _frame(
            [
                ["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000],
                ["vnm", "2024-01-01", 50, 51, 49, 50.5, 500],
                ["hpg", "2024-01-01", 20, 21, 19, 20.5, 700],
            ]
        ),
        merge=False,
    )
    grouped = market_store.frames_by_symbol(["fpt"])
    assert list(grouped) == ["FPT"]


def test_save_and_load_symbols(isolated_store):
    frame = pd.DataFrame({"symbol": ["FPT", "VNM"], "exchange": ["HOSE", "HOSE"]})
    market_store.save_symbols(frame)
    loaded = market_store.load_symbols()
    assert list(loaded["symbol"]) == ["FPT", "VNM"]


# --------------------------------------------------------------- bootstrap()
def test_bootstrap_fetches_full_history_on_empty_store(isolated_store, monkeypatch):
    """bootstrap() phai nap DAY DU (khac refresh(), vo hai tren kho rong) -
    dung khi container khoi dong tren moi truong khong co dia luu ben vung
    (vd Render goi Free) va data/ bi xoa trang."""
    from bot_phan_tich.data import vietcap as vietcap_mod

    symbols_frame = pd.DataFrame({"symbol": ["FPT", "VNM"], "exchange": ["HOSE", "HOSE"]})
    ohlcv_frame = _frame(
        [
            ["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000],
            ["vnm", "2024-01-01", 50, 51, 49, 50.5, 500],
        ]
    )
    calls = {}

    def fake_fetch_all_symbols(exchanges):
        calls["exchanges"] = exchanges
        return symbols_frame

    def fake_fetch_ohlcv_bulk(symbols, count_back):
        calls["symbols"] = symbols
        calls["count_back"] = count_back
        return ohlcv_frame

    monkeypatch.setattr(vietcap_mod, "fetch_all_symbols", fake_fetch_all_symbols)
    monkeypatch.setattr(vietcap_mod, "fetch_ohlcv_bulk", fake_fetch_ohlcv_bulk)

    total = market_store.bootstrap(exchanges=["HOSE"], count_back=750)

    assert total == 2
    assert calls["exchanges"] == ["HOSE"]
    assert set(calls["symbols"]) == {"FPT", "VNM"}
    assert calls["count_back"] == 750
    assert set(market_store.load_ohlcv()["symbol"]) == {"FPT", "VNM"}
    assert list(market_store.load_symbols()["symbol"]) == ["FPT", "VNM"]


def test_bootstrap_saves_incrementally_per_chunk(isolated_store, monkeypatch):
    """Moi lo phai duoc LUU NGAY (khong doi tai het moi luot luu) - neu tien
    trinh bi ngat giua chung (vd Render goi Free restart do vuot RAM), cac lo
    da tai xong van con lai trong kho thay vi mat trang toan bo (da gap thuc
    te: ban goc chi luu 1 lan o cuoi, bi restart giua luc tai la mat het)."""
    from bot_phan_tich.data import vietcap as vietcap_mod

    symbols_frame = pd.DataFrame(
        {"symbol": ["A", "B", "C", "D", "E"], "exchange": ["HOSE"] * 5}
    )
    monkeypatch.setattr(vietcap_mod, "fetch_all_symbols", lambda exchanges: symbols_frame)

    saved_after_each_chunk: list[set] = []

    def fake_fetch_ohlcv_bulk(symbols, count_back):
        rows = [[s.lower(), "2024-01-01", 10, 11, 9, 10.5, 1000] for s in symbols]
        return _frame(rows)

    monkeypatch.setattr(vietcap_mod, "fetch_ohlcv_bulk", fake_fetch_ohlcv_bulk)

    real_save_ohlcv = market_store.save_ohlcv

    def spy_save_ohlcv(frame, merge=True):
        result = real_save_ohlcv(frame, merge=merge)
        saved_after_each_chunk.append(set(market_store.load_ohlcv()["symbol"]))
        return result

    monkeypatch.setattr(market_store, "save_ohlcv", spy_save_ohlcv)

    total = market_store.bootstrap(chunk_size=2)

    assert total == 5
    assert len(saved_after_each_chunk) == 3  # 5 ma, lo 2 -> 3 lo (2, 2, 1)
    # kho PHAI lon dan qua tung lo, khong phai rong het cho toi lo cuoi
    assert saved_after_each_chunk[0] == {"A", "B"}
    assert saved_after_each_chunk[1] == {"A", "B", "C", "D"}
    assert saved_after_each_chunk[2] == {"A", "B", "C", "D", "E"}


def test_bootstrap_count_back_defaults_to_config(isolated_store, monkeypatch):
    """Khong truyen count_back -> lay tu config (ghi de duoc bang MARKET_COUNT_BACK)."""
    from bot_phan_tich.data import vietcap as vietcap_mod

    monkeypatch.setenv("MARKET_COUNT_BACK", "321")
    monkeypatch.setattr(
        vietcap_mod, "fetch_all_symbols",
        lambda exchanges: pd.DataFrame({"symbol": ["FPT"], "exchange": ["HOSE"]}),
    )
    seen = {}

    def fake_fetch_ohlcv_bulk(symbols, count_back):
        seen["count_back"] = count_back
        return _frame([["fpt", "2024-01-01", 10, 11, 9, 10.5, 1000]])

    monkeypatch.setattr(vietcap_mod, "fetch_ohlcv_bulk", fake_fetch_ohlcv_bulk)

    market_store.bootstrap()

    assert seen["count_back"] == 321


def test_bootstrap_returns_zero_when_symbol_list_empty(isolated_store, monkeypatch):
    from bot_phan_tich.data import vietcap as vietcap_mod

    monkeypatch.setattr(vietcap_mod, "fetch_all_symbols", lambda exchanges: pd.DataFrame())

    total = market_store.bootstrap()

    assert total == 0
    assert market_store.load_ohlcv().empty
