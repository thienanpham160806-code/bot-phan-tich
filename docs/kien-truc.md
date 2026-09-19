# Kien truc he thong

```
                    +--------------------------+
   DNSE OpenAPI --> |                          |
                    |   data/  (router)        |  uu tien -> du phong -> cache
   Vietcap/VCI  --> |  base, dnse, vietcap,    |
   (chua co API) --> |  cleaner, cache, universe|
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
                    |  lookup    - ho so + chi so + cap nhat
                    |  screener  - loc ky thuat + co ban
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
                    |  bot/  (aiogram)         |
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
5. **Moi nguong nam trong `config/settings.yaml`,** khong hard-code trong ma
   nguon (trong so cham diem, nguong RSI thich ung, tham so Ichimoku, timeout
   cua screener...).
6. **`alerts/` khong goi Telegram API.** `run_eod_scan()` chi tra ve du lieu
   can gui; `bot/main.py` moi thuc su goi `bot.send_message()`.

## Luong mot phien quet cuoi ngay (alerts/eod.py)

1. `scheduler` kich hoat theo `bot.scan_cron` (mac dinh 15h05 cac ngay lam viec).
2. `alerts.eod.run_eod_scan()` lay danh sach ma dang duoc theo doi
   (`alerts.watchlist.all_subscriptions()`).
3. Voi moi ma: nap gia qua `data.router`, chay `analysis.scoring.recommend()`,
   so voi trang thai luu lan truoc (bang `signals`, cot `payload`).
4. Chi giu lai ma co thay doi dang chu y (doi bac khuyen nghi, giao cat MACD
   moi, xuyen may Kumo, RSI vao/ra cuc tri, khoi luong dot bien, gia bien dong
   manh) - toi da 3 canh bao/ma/ngay.
5. Gop tat ca ma co thay doi cua CUNG mot `chat_id` thanh MOT tin nhan.
6. `bot/main.py` gui tin qua `bot.send_message()`.

## Luong lenh /khuyennghi

1. Handler nap gia qua `data.router.ohlcv()`.
2. `analysis.scoring.recommend()` chay ca ba `indicators/` (macd_state,
   rsi_state, ichimoku_state) + `indicators.divergence.detect_divergence()`.
3. Gop diem co trong so, ap quy tac hop luu (phu quyet Ichimoku, tru diem
   phan ky am, ha do tin cay khi khoi luong thap).
4. Tra ve `Recommendation` (dataclass) -> `bot.formatters.recommendation_card()`.
