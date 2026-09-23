import pytest

from bot_phan_tich import diagnostics
from bot_phan_tich.analysis import snapshot as snapshot_mod
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
    monkeypatch.setattr(snapshot_mod, "_status", snapshot_mod.BuildStatus())


def _fake_files(monkeypatch, files: dict[str, str]):
    def read_first(*paths):
        return next((files[p] for p in paths if p in files), None)

    monkeypatch.setattr(diagnostics, "_read_first", read_first)


def test_cgroup_v2_limits_are_read(monkeypatch):
    _fake_files(
        monkeypatch,
        {
            "/sys/fs/cgroup/memory.max": str(512 * 1_048_576),
            "/sys/fs/cgroup/cpu.max": "50000 100000",
        },
    )
    assert diagnostics._cgroup_memory_limit_mb() == 512
    assert diagnostics._cgroup_cpu_quota() == 0.5


def test_cgroup_unlimited_is_none(monkeypatch):
    _fake_files(
        monkeypatch, {"/sys/fs/cgroup/memory.max": "max", "/sys/fs/cgroup/cpu.max": "max 100000"}
    )
    assert diagnostics._cgroup_memory_limit_mb() is None
    assert diagnostics._cgroup_cpu_quota() is None


def test_cgroup_v1_limits_are_read(monkeypatch):
    _fake_files(
        monkeypatch,
        {
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(256 * 1_048_576),
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "200000",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000",
        },
    )
    assert diagnostics._cgroup_memory_limit_mb() == 256
    assert diagnostics._cgroup_cpu_quota() == 2.0


def test_offline_diagnostics_on_empty_bot(isolated):
    checks = diagnostics.run_diagnostics(network=False)
    names = [c.name for c in checks]
    assert names == ["RAM", "CPU", "Cấu hình quy mô", "Kho giá", "Snapshot"]
    table = diagnostics.format_table(checks)
    assert "trống" in table and "chưa có" in table


def test_vietcap_empty_200_is_reported_as_failure(monkeypatch):
    """HTTP 200 nhung danh sach rong = dau hieu bi chan/sai header - phai bao LOI."""
    from bot_phan_tich.data import vietcap

    monkeypatch.setattr(vietcap, "probe_endpoint", lambda *a, **k: (200, [], None))
    check = diagnostics.check_vietcap_listing()
    assert check.status == diagnostics.FAIL
    assert "RỖNG" in check.detail


def test_dnse_without_keys_is_informational(monkeypatch):
    from bot_phan_tich.config import Secrets

    monkeypatch.setattr(diagnostics, "get_secrets", lambda: Secrets())
    check = diagnostics.check_dnse()
    assert check.status == diagnostics.INFO


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


async def test_trangthai_chandoan_runs_diagnostics(monkeypatch):
    monkeypatch.setattr(
        status_handlers, "run_diagnostics",
        lambda: [diagnostics.Check("Vietcap getAll", diagnostics.FAIL, "HTTP 403 <chan>")],
    )
    message = FakeMessage("/trangthai chandoan")
    await status_handlers.cmd_status(message)
    assert message.answers[-1].startswith("<pre>")
    assert "HTTP 403 &lt;chan&gt;" in message.answers[-1]
