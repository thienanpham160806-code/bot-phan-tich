"""Keo du lieu TOAN SAN tu endpoint cong khai cua bang gia Vietcap.

Ba buoc, moi buoc goi theo LO (nhieu ma mot request) thay vi tung ma:

  1. Danh sach ma      GET  /price/symbols/getAll            -> 1 request cho ca san
  2. Anh chup gia      POST /price/symbols/getList           -> ~100 ma / request
  3. Lich su OHLCV     POST /chart/OHLCChart/gap-chart       -> ~20 ma / request

Ket qua ghi ra data/vietcap/*.parquet, dung lam kho du lieu cuc bo cho bot.

Cach chay:
    python scripts/fetch_all_vietcap.py                      # ca 3 buoc, 500 phien
    python scripts/fetch_all_vietcap.py --bars 750           # ~3 nam lich su
    python scripts/fetch_all_vietcap.py --only symbols snapshot
    python scripts/fetch_all_vietcap.py --exchanges HOSE HNX # bo UPCOM

LUU Y:
  - Day la endpoint CONG KHAI ma trang bang gia tu goi, khong can dang nhap.
    Khong dung token cua tai khoan chung khoan o day.
  - Endpoint khong co tai lieu, co the doi bat cu luc nao. Cau truc phan hoi
    duoc doc theo ma nguon cua vnstock (thinh-vu/vnstock, explorer/vci/).
  - Kich thuoc lo tu dong CHIA DOI khi server tu choi, nen khong can biet
    truoc gioi han that cua Vietcap.
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://trading.vietcap.com.vn/api"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
OUT_DIR = Path("data/vietcap")
EXCHANGE_ALIAS = {"HSX": "HOSE", "HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM"}

session = requests.Session()
session.headers.update(HEADERS)


# --------------------------------------------------------------------- helpers
def polite_sleep(base: float) -> None:
    """Gian nhip co nhieu ngau nhien de khong goi dong loat."""
    time.sleep(base + random.uniform(0, base))


def request_json(method: str, url: str, payload: dict | None = None,
                 attempts: int = 5, delay: float = 1.0):
    """Goi API kem lui theo cap so nhan khi gap 429/5xx hoac loi mang."""
    for attempt in range(1, attempts + 1):
        try:
            resp = session.request(method, url, json=payload, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == attempts:
                raise
            wait = delay * 2 ** (attempt - 1)
            print(f"    loi ({exc}), thu lai sau {wait:.0f}s [{attempt}/{attempts}]")
            time.sleep(wait)


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_in_batches(symbols: list[str], batch_size: int, fetch_one_batch,
                     label: str, delay: float) -> list:
    """Chay theo lo; lo nao loi thi chia doi va thu lai, toi thieu 1 ma."""
    results: list = []
    queue = list(chunks(symbols, batch_size))
    done = 0
    while queue:
        batch = queue.pop(0)
        try:
            results.extend(fetch_one_batch(batch))
            done += len(batch)
            print(f"  [{label}] {done}/{len(symbols)} ma")
        except Exception as exc:
            if len(batch) == 1:
                print(f"  [{label}] bo qua {batch[0]}: {exc}")
                done += 1
            else:
                half = len(batch) // 2
                print(f"  [{label}] lo {len(batch)} ma bi tu choi -> chia doi")
                queue[:0] = [batch[:half], batch[half:]]
        polite_sleep(delay)
    return results


# ------------------------------------------------------------ 1. danh sach ma
def fetch_symbols(exchanges: list[str]) -> pd.DataFrame:
    print("1/3  Lay danh sach ma toan san...")
    raw = request_json("GET", f"{BASE}/price/symbols/getAll")
    frame = pd.DataFrame(raw if isinstance(raw, list) else raw.get("data", []))
    if frame.empty:
        raise SystemExit("Khong lay duoc danh sach ma. Endpoint co the da doi.")

    exch_col = next((c for c in ("board", "exchange", "floor") if c in frame.columns), None)
    if exch_col:
        frame["exchange"] = frame[exch_col].astype(str).str.upper().map(EXCHANGE_ALIAS)
        frame = frame[frame["exchange"].isin(exchanges)]

    type_col = next((c for c in ("type", "securityType", "stockType") if c in frame.columns), None)
    if type_col:
        frame = frame[frame[type_col].astype(str).str.upper().str.contains("STOCK")]

    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame = frame[frame["symbol"].str.fullmatch(r"[A-Z0-9]{3}")]   # ma co phieu 3 ky tu
    frame = frame.drop_duplicates("symbol").reset_index(drop=True)
    print(f"     {len(frame)} ma co phieu tren {', '.join(exchanges)}")
    return frame


# ------------------------------------------------------------ 2. anh chup gia
def fetch_snapshot(symbols: list[str], batch_size: int, delay: float) -> pd.DataFrame:
    print(f"2/3  Lay anh chup gia toan san ({batch_size} ma/request)...")

    def one_batch(batch: list[str]) -> list[dict]:
        raw = request_json("POST", f"{BASE}/price/symbols/getList", {"symbols": batch})
        return raw if isinstance(raw, list) else raw.get("data", [])

    rows = fetch_in_batches(symbols, batch_size, one_batch, "snapshot", delay)
    # Phan hoi long nhau (listingInfo / bidAsk / matchPrice) -> lam phang
    frame = pd.json_normalize(rows, sep=".")
    print(f"     {len(frame)} dong, {len(frame.columns)} cot")
    return frame


# ------------------------------------------------------------ 3. lich su OHLCV
def fetch_history(symbols: list[str], bars: int, batch_size: int,
                  delay: float) -> pd.DataFrame:
    print(f"3/3  Lay lich su {bars} phien ({batch_size} ma/request)...")
    to_ts = int(time.time())

    def one_batch(batch: list[str]) -> list[pd.DataFrame]:
        payload = {"timeFrame": "ONE_DAY", "symbols": batch,
                   "to": to_ts, "countBack": bars}
        raw = request_json("POST", f"{BASE}/chart/OHLCChart/gap-chart", payload)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        frames = []
        for i, item in enumerate(items):
            if not item or "t" not in item:
                continue
            sym = str(item.get("symbol") or batch[i]).upper()
            frames.append(pd.DataFrame({
                "symbol": sym,
                "time": pd.to_datetime(pd.Series(item["t"], dtype="int64"), unit="s"),
                "open": item.get("o"), "high": item.get("h"),
                "low": item.get("l"), "close": item.get("c"),
                "volume": item.get("v"),
            }))
        return frames

    parts = fetch_in_batches(symbols, batch_size, one_batch, "history", delay)
    if not parts:
        return pd.DataFrame(columns=["symbol", "time", "open", "high", "low", "close", "volume"])
    frame = pd.concat(parts, ignore_index=True)
    frame = frame.drop_duplicates(["symbol", "time"]).sort_values(["symbol", "time"])
    print(f"     {frame['symbol'].nunique()} ma, {len(frame):,} dong")
    return frame.reset_index(drop=True)


# ----------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description="Keo du lieu toan san tu Vietcap")
    parser.add_argument("--exchanges", nargs="+", default=["HOSE", "HNX", "UPCOM"])
    parser.add_argument("--bars", type=int, default=500, help="so phien lich su")
    parser.add_argument("--only", nargs="+", choices=["symbols", "snapshot", "history"])
    parser.add_argument("--snapshot-batch", type=int, default=100)
    parser.add_argument("--history-batch", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0, help="giay nghi giua cac request")
    args = parser.parse_args()

    steps = set(args.only or ["symbols", "snapshot", "history"])
    exchanges = [e.upper() for e in args.exchanges]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()

    symbols_path = OUT_DIR / "symbols.parquet"
    if "symbols" in steps or not symbols_path.exists():
        listing = fetch_symbols(exchanges)
        listing.to_parquet(symbols_path, index=False)
    else:
        listing = pd.read_parquet(symbols_path)
    symbols = listing["symbol"].tolist()

    if "snapshot" in steps:
        fetch_snapshot(symbols, args.snapshot_batch, args.delay).to_parquet(
            OUT_DIR / "snapshot.parquet", index=False)

    if "history" in steps:
        fetch_history(symbols, args.bars, args.history_batch, args.delay).to_parquet(
            OUT_DIR / "ohlcv.parquet", index=False)

    print(f"\nXong sau {(time.time() - started) / 60:.1f} phut. Du lieu o {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
