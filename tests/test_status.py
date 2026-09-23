import pandas as pd
import pytest

from bot_phan_tich.analysis import snapshot as snapshot_mod
from bot_phan_tich.bot.formatters import status_card
from bot_phan_tich.bot.handlers import screener as screener_handlers
from bot_phan_tich.bot.handlers import signals as signals_handlers
from bot_phan_tich.bot.handlers import status as status_handlers
from bot_phan_tich.config import Paths
from bot_phan_tich.data import fundamentals_store, market_store


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    for mod in (market_store, snapshot_mod, fundamentals_store):
        monkeypatch.setattr(mod, "get_paths", lambda: paths)
    market_store._cache.clear()
    fundamentals_store._cache.clear()
    status = snapshot_mod.BuildStatus()
    monkeypatch.setattr(snapshot_mod, "_status", status)
    return status


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.answers.append(text)


def test_status_card_on_empty_bot(isolated):
    text = status_card(status_handlers.collect_system_status())
    assert "Kho giá" in text and "Trống" in text
    assert "Snapshot khuyến nghị" in text and "Chưa có" in text
    assert "Chưa chạy lần nào" in text
    assert "RAM tiến trình" in text


def test_status_card_shows_store_counts_and_last_error(isolated):
    market_store.save_ohlcv(
        pd.DataFrame(
            [
                ["FPT", "2024-01-01", 10, 11, 9, 10.5, 1000],
                ["FPT", "2024-01-02", 10, 11, 9, 10.6, 1000],
                ["VNM", "2024-01-01", 50, 51, 49, 50.5, 500],
            ],
            columns=market_store.OHLCV_COLUMNS,
        ),
        merge=False,
    )
    isolated.finished_at = snapshot_mod._as_local(None)
    isolated.last_error = "ConnectionError: <timeout>"

    text = status_card(status_handlers.collect_system_status())

    assert "2 mã, 3 dòng" in text
    assert "Thất bại" in text
    assert "ConnectionError: &lt;timeout&gt;" in text  # loi phai duoc escape HTML


async def test_loc_without_data_explains_progress(isolated):
    isolated.running = True
    isolated.step = snapshot_mod.STEP_BOOTSTRAP
    isolated.done, isolated.total = 450, 1500

    message = FakeMessage("/loc san=HOSE kn=MUA")
    await screener_handlers.cmd_screen(message)

    assert len(message.answers) == 1
    assert "Đang nạp kho giá toàn sàn: 450/1500 mã" in message.answers[0]


async def test_tinhieu_without_data_shows_last_error(isolated):
    isolated.finished_at = snapshot_mod._as_local(None)
    isolated.last_error = "ConnectionError: Vietcap timeout"

    message = FakeMessage("/tinhieu")
    await signals_handlers.cmd_signals(message)

    assert "thất bại" in message.answers[0]
    assert "Vietcap timeout" in message.answers[0]
    assert "/trangthai" in message.answers[0]
