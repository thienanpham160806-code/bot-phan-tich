# Kien truc he thong

## Luong du lieu chinh: Vietcap/DNSE -> market_store -> snapshot -> bot doc bang

Day la thay doi kien truc quan trong nhat cua du an (giai quyet triet de van
de "/loc treo bot" va "chi co 13 ma"): moi tinh toan NANG (goi mang, tinh
chi bao) deu duoc lam TRUOC va MOT LAN, o NGOAI luong xu ly tin nhan Telegram.
Luc bot dang tra loi nguoi dung, no chi DOC BANG co san - khong bao gio tu
tinh lai hay goi mang trong luc dang phuc vu mot lenh.

```
  Vietcap (endpoint cong khai)      DNSE OpenAPI
  fetch_all_symbols()               (tung ma, khi can)
  fetch_ohlcv_bulk()
         |                                |
         v                                v
  +----------------------------------------------------+
  |  data/market_store.py                              |
  |  MOT FILE PARQUET DUY NHAT: data/market/ohlcv.parquet|
  |  Toan bo lich su gia CA SAN (HOSE/HNX/UPCOM)        |
  +----------------------------+-----------------------+
                                |
        scripts/backfill_data.py (lan dau: toan bo lich su,
        cac lan sau: chi tai them vai phien moi, gop vao kho cu)
                                |
                                v
  +----------------------------------------------------+
  |  analysis/snapshot.py :: build_snapshot()           |
  |  Voi MOI ma du dieu kien thanh khoan (data/universe.py):|
  |    - doc kho MOT LAN (frames_by_symbol), khong goi mang|
  |    - goi analysis/scoring.py :: recommend() DUNG 1 LAN|
  |    - duyet TUAN TU trong MOT tien trinh (~15 ms/ma) |
  |  Ghi ra data/market/snapshot.parquet                |
  +----------------------------+-----------------------+
                                |
        scripts/build_snapshot.py (thu cong), HOAC tu dong qua
        analysis/snapshot.py :: update_market_data() (mot luong duy nhat,
        co khoa chong chay chong, ghi tien do/loi cho /trangthai):
          - bot/scheduler.py: sau gio dong cua moi ngay (bot.scan_cron, 15h05)
            va sau phien sang (bot.midday_cron, 11h35 - ban "tam tinh":
            nen hom nay chua dong, 15h05 tai lai va ghi de)
          - bot/main.py: ensure_fresh_in_background() luc bot khoi dong,
            neu kho rong / snapshot cu / snapshot tam (KHONG chan bot)
                                |
                                v
  +----------------------------------------------------+
  |  analysis/screener.py (/loc), today_signals() (/tinhieu)|
  |  CHI DOC snapshot.parquet bang pandas boolean mask  |
  |  KHONG tinh lai, KHONG goi mang -> xong duoi 1 giay |
  +----------------------------+-----------------------+
                                |
                                v
                    bot/handlers/ (aiogram, polling)
```

Cac lenh KHONG di qua snapshot (vd `/khuyennghi`, `/bieudo`, `/tracuu` cho
MOT ma cu the) van tinh `recommend()` truc tiep tren du lieu cua rieng ma do
(qua `data/router.py`, uu tien doc tu `market_store` truoc, chi goi mang khi
ma khong co san) - nhung luon chay trong thread rieng
(`await asyncio.to_thread(...)`) de khong chan event loop cua bot trong luc
tinh, cho phep `/help` va cac lenh khac van tra loi ngay lap tuc song song
(xem `tests/test_nonblocking.py`).

## So do module

```
                    +--------------------------+
   DNSE OpenAPI --> |                          |
                    |   data/  (router)        |  uu tien -> du phong -> cache
   Vietcap/VCI  --> |  base, dnse, vietcap,    |
                    |  cleaner, cache, universe|
                    |  market_store (kho toan san)|
                    |  fundamentals_store      |
                    |  realtime.py (STUB)      |
                    +------------+-------------+
                                 |
                    +------------v-------------+
                    |  indicators/             |  point-in-time, tu cai
                    |  common, macd, rsi,      |  bang pandas/numpy
                    |  ichimoku, divergence    |
                    +------------+-------------+
                                 |
                    +------------v-------------+
                    |  analysis/               |
                    |  scoring   - hop luu 3 he -> khuyen nghi
                    |  snapshot  - tinh san khuyen nghi toan san
                    |  screener  - loc CHI DOC snapshot
                    |  lookup    - ho so + chi so + cap nhat
                    |  fintext   - text mining BCTC
                    +------------+-------------+
                                 |
              +------------------+------------------+
              |                                     |
   +----------v----------+              +-----------v----------+
   |  alerts/             |              |  risk/  sizing,       |
   |  watchlist, eod      |              |         stops,        |
   |  (quet cuoi phien)   |              |         constraints   |
   +----------------------+              +----------------------+
              |                                     |
              +------------------+------------------+
                                 |
                    +------------v-------------+
                    |  backtest/  engine,      |
                    |  metrics, walk_forward,  |
                    |  signals (cau noi voi    |
                    |  analysis/scoring.py)    |
                    +------------+-------------+
                                 |
                    +------------v-------------+
                    |  bot/  (aiogram, polling)|
                    |  handlers/, charts,      |
                    |  formatters, scheduler   |
                    +--------------------------+
```

## Nguyen tac thiet ke

1. **Ba he chi bao doc lap, gop co trong so, co quyen phu quyet.** MACD va RSI
   la chi bao dong luc don le; Ichimoku la he thong xu huong hoan chinh va co
   quyen chan khuyen nghi MUA khi gia duoi may Kumo, bat ke diem tong cao bao
   nhieu. Xem `analysis/scoring.py`.
2. **`indicators/` chi tinh toan, khong quyet dinh.** Moi ham nhan DataFrame
   gia, tra ve Series/DataFrame cung do dai. Logic "diem bao nhieu thi MUA/BAN"
   nam rieng o `analysis/scoring.py`.
3. **Phan con lai cua he thong khong biet du lieu den tu dau.** Tat ca di qua
   `data/router.py`. Realtime (`data/realtime.py`) la GIAO DIEN, mac dinh tat
   (`realtime.enabled: false`) - bot luon chay duoc bang du lieu cuoi phien.
4. **Khong module nao duoc goi mang truc tiep, tru `data/`.**
5. **Tinh toan nang duoc lam TRUOC, MOT LAN, NGOAI luong tra loi Telegram.**
   `market_store` (kho gia) va `snapshot` (khuyen nghi toan san) deu la du
   lieu duoc "dung san" (precomputed) - handler chi doc bang, khong tinh lai.
6. **Handler khong bao gio chan event loop.** Moi ham nang (lookup, recommend,
   fintext, ve bieu do, quet watchlist) deu boc bang `await asyncio.to_thread(...)`.
7. **Moi nguong nam trong `config/settings.yaml`,** khong hard-code trong ma
   nguon (trong so cham diem, nguong RSI thich ung, tham so Ichimoku, cac
   dieu kien cua 3 bo loc dung san...).
8. **`alerts/` khong goi Telegram API.** `run_eod_scan()` chi tra ve du lieu
   can gui; `bot/main.py` moi thuc su goi `bot.send_message()`.
9. **Khong bao gio bia du lieu.** Truong nao khong lay duoc thi de `None` /
   "khong co du lieu" - ap dung cho ca gia, chi so co ban, va tin tuc.

## Luong `scripts/build_snapshot.py` (hoac tu dong hang ngay)

1. `data/universe.py::liquid_universe()` doc `market_store` (chi cac cot
   can, khong goi mang), loc theo san/gia/khoi luong/so ngay niem yet tu
   `config/settings.yaml`; neu `universe.max_symbols > 0` chi giu N ma
   thanh khoan nhat.
2. `analysis/snapshot.py::build_snapshot()` doc kho MOT LAN
   (`frames_by_symbol`), duyet TUAN TU trong mot tien trinh: moi ma goi
   `analysis.scoring.recommend()` DUNG MOT LAN, gop them chi so co ban tu
   `fundamentals_store` (neu co). Khong dung da tien trinh: ban cu mo
   `os.cpu_count() - 1` tien trinh, moi tien trinh tu doc lai ca kho
   (~111 MB) -> vuot 512 MB cua Render goi Free -> OOM -> lap vo tan.
3. Ghi ra `data/market/snapshot.parquet` (~24 cot: hanh dong, diem, trang
   thai MACD/RSI/Ichimoku, ly do, thoi diem tinh `as_of`...).

## Cap nhat du lieu o nen: `analysis/snapshot.py::update_market_data()`

Mot luong DUY NHAT cho ca luc khoi dong (`ensure_fresh_in_background()`),
lich 11h35 (`bot/main.py::midday_update_job()`) va lich 15h05
(`bot/main.py::daily_scan_job()`), co `asyncio.Lock` de cac luong khong ghi
chong len cung mot file:

1. Kho gia RONG (lan dau, hoac Render goi Free vua restart - dia tam bi xoa):
   a. TRUOC TIEN dung snapshot TAM cho danh sach theo doi trong
      `config/universe.yaml` (~12 ma, vai giay) - `/loc`, `/tinhieu` co ket
      qua that ngay, kem ghi chu "Du lieu tam thoi: N ma". Ban tam danh dau
      bang file `snapshot.partial`, KHONG ghi vao kho gia.
   b. `market_store.bootstrap()` nap toan san: tai tung lo, ghi noi tiep
      vao file tam, xong het moi doi ten thanh kho that - kho hoac chua co,
      hoac du ca san (khong bao gio "ket" o mot phan).
2. Kho da co: `market_store.refresh()` tai bu vai phien moi nhat, gop vao kho
   o dang tiet kiem RAM (category + float32).
3. `build_snapshot()` dung snapshot day du, xoa dau "tam thoi".

Moi buoc cap nhat `BuildStatus` (buoc hien tai, x/y ma, uoc tinh thoi gian
con lai, loi gan nhat) - hien trong `/trangthai` va trong thong bao cua
`/loc`, `/tinhieu` khi chua co du lieu. Do moi cua du lieu (`is_stale()`)
tinh theo gio `bot.timezone` (Viet Nam), khong theo gio may chu (Render UTC).

## Luong lenh `/loc`, `/tinhieu`

1. Neu chua co snapshot: tra loi ro ly do - dang nap den dau ("Dang nap kho
   gia toan san: 450/1500 ma (khoang 2 phut nua)") hoac lan truoc loi gi.
2. `analysis.screener.screen_report()` / `today_signals()` doc
   `snapshot.parquet` MOT LAN, loc/nhom bang pandas boolean mask, kem ghi
   chu neu du lieu la ban tam, dang cap nhat o nen, hoac da cu.
3. Ca hai deu chay trong `await asyncio.to_thread(...)` (du ban than da rat
   nhanh - duoi 1 giay tren du lieu thuc te) de nhat quan voi nguyen tac 6.
4. Ket qua qua `bot/formatters.py:screener_results_card()` / `signals_card()`.

## Luong lenh `/khuyennghi`, `/bieudo` (mot ma cu the)

1. Handler nap gia qua `data.router.ohlcv()` (uu tien doc tu `market_store`).
2. `analysis.scoring.recommend()` chay ca ba `indicators/` (macd_state,
   rsi_state, ichimoku_state) + `indicators.divergence.detect_divergence()`.
3. Gop diem co trong so, ap quy tac hop luu (phu quyet Ichimoku, tru diem
   phan ky am, ha do tin cay khi khoi luong thap).
4. Tra ve `Recommendation` (dataclass) -> `bot.formatters.recommendation_card()`.

Ca 4 buoc tren chay trong `await asyncio.to_thread(...)` trong handler.
