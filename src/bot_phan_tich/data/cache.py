"""Cache hai tang: SQLite cho sieu du lieu, Parquet cho chuoi gia dai."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from ..config import get_paths
from ..logging_conf import get_logger

log = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_meta (
    key         TEXT PRIMARY KEY,
    updated_at  REAL NOT NULL,
    rows        INTEGER
);

CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id     INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (chat_id, symbol)
);

CREATE TABLE IF NOT EXISTS signals (
    trade_date  TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    probability REAL,
    entry       REAL,
    stop_loss   REAL,
    target      REAL,
    payload     TEXT,
    PRIMARY KEY (trade_date, symbol, side)
);

CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(trade_date);

-- alerts/eod.py dung cot payload (JSON) de luu trang thai khuyen nghi gan
-- nhat cua moi ma (side = 'eod'), lam co so so sanh cho lan quet ke tiep.

CREATE TABLE IF NOT EXISTS alert_settings (
    chat_id     INTEGER PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1
);
"""


@contextmanager
def connect():
    path = get_paths().cache_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    log.info("Da khoi tao CSDL tai %s", get_paths().cache_db)


# ----------------------------------------------------------------- parquet cache
def _parquet_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return get_paths().data_dir / "parquet" / f"{safe}.parquet"


def write_frame(key: str, frame: pd.DataFrame) -> None:
    path = _parquet_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    with connect() as conn:
        conn.execute(
            "INSERT INTO cache_meta(key, updated_at, rows) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET updated_at=excluded.updated_at, rows=excluded.rows",
            (key, time.time(), len(frame)),
        )


def read_frame(key: str, max_age: float | None = None) -> pd.DataFrame | None:
    """Doc cache. Tra None neu chua co hoac da qua han max_age giay."""
    path = _parquet_path(key)
    if not path.exists():
        return None
    if max_age is not None:
        with connect() as conn:
            row = conn.execute(
                "SELECT updated_at FROM cache_meta WHERE key = ?", (key,)
            ).fetchone()
        if row and (time.time() - row["updated_at"]) > max_age:
            return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover
        log.warning("Doc cache %s that bai: %s", key, exc)
        return None


def age_seconds(key: str) -> float | None:
    with connect() as conn:
        row = conn.execute("SELECT updated_at FROM cache_meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else time.time() - row["updated_at"]
