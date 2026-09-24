# bot-phan-tich

Telegram Bot phân tích kỹ thuật chứng khoán Việt Nam — hợp lưu ba hệ chỉ báo
**MACD, RSI (ngưỡng thích ứng), Ichimoku Kinko Hyo** — trên **toàn sàn**
HOSE/HNX/UPCOM (không chỉ vài mã theo dõi mẫu).

Kiến trúc cốt lõi: dữ liệu giá toàn sàn được nạp một lần vào một kho parquet
duy nhất (`data/market_store.py`), khuyến nghị của **từng mã** được tính sẵn
**một lần cuối mỗi phiên** thành "snapshot" (`analysis/snapshot.py`) — nên
`/loc` và `/tinhieu` chỉ **đọc bảng có sẵn**, trả lời dưới 1 giây, và bot
**không bao giờ bị treo** dù đang quét toàn sàn ở nền (mọi việc nặng đều chạy
qua `asyncio.to_thread`/tiến trình riêng — xem [docs/kien-truc.md](docs/kien-truc.md)).

---

## 1. Cài đặt

Yêu cầu Python 3.10+.

```bash
git clone https://github.com/thienanpham160806-code/bot-phan-tich.git
cd bot-phan-tich

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

---

## 2. Cấu hình `.env`

Mở `.env` và điền:

| Biến | Lấy ở đâu |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Chat với [@BotFather](https://t.me/BotFather) trên Telegram, lệnh `/newbot` |
| `DNSE_API_KEY`, `DNSE_API_SECRET` | EntradeX → mục LightSpeed API (xem hướng dẫn bên dưới) — **tuỳ chọn** |
| `VNSTOCK_ACCEPT_TOS` | Đặt `1` sau khi chạy `register_user()` của vnstock một lần |

> **Không bao giờ** commit file `.env`. File này đã nằm trong `.gitignore`
> (chỉ `.env.example` — bản mẫu rỗng — mới được commit).

Chưa có `DNSE_API_KEY`/`DNSE_API_SECRET` cũng không sao — `data/router.py`
tự động dùng nguồn dự phòng (Vietcap/VCI qua `vnstock`, không cần API key)
nên bot vẫn chạy được đầy đủ phần dữ liệu cuối phiên. Xem bảng nguồn dữ liệu
ở mục 6.

### Cách lấy API key DNSE (nếu muốn dùng nguồn chính)

1. Mở tài khoản chứng khoán online tại <https://www.dnse.com.vn> (eKYC bằng
   CCCD gắn chip), không cần nạp tiền để dùng phần dữ liệu thị trường.
2. Đăng nhập **EntradeX** (<https://banggia.dnse.com.vn> hoặc app EntradeX)
   → mục **LightSpeed API** trong cài đặt tài khoản → tạo khoá.
3. **API secret chỉ hiện đúng một lần** — copy ngay vào `.env`, lỡ mất phải
   tạo khoá mới. Không thấy mục LightSpeed API thì liên hệ DNSE (hotline
   024 7108 9234 / hello@dnse.com.vn), cung cấp số tài khoản 064C + họ tên.
4. `pip install openapi-sdk` (theo docs của DNSE) **không cài được** — tên
   gói đó chỉ là ví dụ trong docs, không phải tên thật trên PyPI. Tên gói
   PyPI thật là `dnse-sdk-openapi` (đã có sẵn trong `requirements.txt`,
   không cần cài riêng — xem `data/dnse.py`).

Cấu hình Vietcap (nguồn dự phòng, **không cần API key**): qua thư viện
`vnstock` — `pip install -U vnstock` (đã có trong `requirements.txt`), chạy
`register_user()` một lần, đặt `VNSTOCK_ACCEPT_TOS=1` trong `.env`.

> Lỡ commit lộ `DNSE_API_KEY`/`DNSE_API_SECRET` lên Git: vào EntradeX **tạo
> khoá mới ngay** (khoá cũ coi như đã lộ) rồi mới dọn lịch sử commit — đổi
> khoá trước, dọn git sau.

---

## 3. Nạp dữ liệu và chạy bot

Ba bước theo đúng thứ tự. Nếu bỏ qua bước 1 và 2, bot vẫn tự nạp khi khởi
động (dùng tạm ~12 mã trong danh sách theo dõi trong vài giây đầu, rồi nạp
toàn sàn ở nền — theo dõi bằng `/trangthai`), nhưng chạy trước sẽ có ngay
dữ liệu đầy đủ:

```bash
# 1. Nạp giá TOÀN SÀN (HOSE/HNX/UPCOM) vào kho parquet cục bộ (data/market/ohlcv.parquet).
#    Lần đầu tải 500 phiên (~2 năm)/mã cho ~1.500 mã — mất khoảng 2 phút,
#    tuỳ tốc độ mạng (500 phiên vẫn dư cho mọi chỉ báo: Ichimoku cần 52+26,
#    RSI thích ứng cần 252). Các lần sau chỉ tải thêm vài phiên mới nhất và
#    gộp vào kho cũ — vài chục giây. Số phiên chỉnh ở config/settings.yaml
#    (market_store.count_back_bootstrap) hoặc biến MARKET_COUNT_BACK.
python scripts/backfill_data.py

# 2. Tính khuyến nghị (MACD/RSI/Ichimoku hợp lưu) cho MỌI mã đủ điều kiện
#    thanh khoản, MỘT LẦN, chạy song song nhiều tiến trình. Ghi ra
#    data/market/snapshot.parquet — đây là bảng mà /loc và /tinhieu đọc.
#    Đo thực tế: 221 mã trong 6,5 giây.
python scripts/build_snapshot.py

# 3. Chạy bot (polling — xem mục 7 để biết vì sao không cần server).
python -m bot_phan_tich.bot.main
```

Tuỳ chọn thêm (không bắt buộc để bot chạy được):

```bash
# Chỉ số cơ bản (P/E, P/B, ROE) cho vu tru thanh khoan — bổ sung điều kiện
# lọc pe=/roe= trong /loc. Cache 7 ngày, tự bỏ qua nếu chạy lại quá sớm.
python scripts/backfill_fundamentals.py

# Backtest chiến lược 3 và 6 tháng gần nhất, so với mua-và-giữ VN-Index.
# Xuất outputs/backtest_3m.csv, backtest_6m.csv, outputs/equity_curve.png.
python scripts/run_backtest.py
```

Kiểm thử: `pytest -q`. Chất lượng mã: `ruff check src tests scripts`.

Trên Windows có thể dùng script tác vụ cho gọn (`.\tasks.ps1 <task>` — xem
`tasks.ps1` để biết danh sách đầy đủ).

---

## 4. Bộ lệnh bot

Giao diện bot được thiết kế theo 3 nhóm nhu cầu cốt lõi, hỗ trợ lệnh ngắn gọn (chạm 1-chạm sao chép):

### 🎯 Nhóm 1: Phân tích 1 cổ phiếu cụ thể
| Lệnh ngắn | Bí danh | Chức năng |
|---|---|---|
| `/kn MA` | `/khuyennghi`, `/rec` | Khuyến nghị MUA/BÁN/THEO DÕI, kế hoạch giá (vào/cắt lỗ %/mục tiêu %), R:R, tỷ trọng giải ngân và lời khuyên F0 |
| `/chart MA` | `/bieudo` | Biểu đồ nến kỹ thuật tích hợp mây Ichimoku, MACD, RSI |
| `/info MA` | `/tracuu` | Hồ sơ niêm yết, định giá P/E, P/B, ROE, vốn hoá chuẩn xác và tin tức công bố thông tin gắn link báo chí |
| `/fin MA` | `/bctc` | Bóc tách BCTC, cơ cấu nợ vay và rủi ro thuyết minh (gửi kèm PDF BCTC nếu có) |

### 🔍 Nhóm 2: Tìm cơ hội đầu tư & Thông tin toàn sàn
| Lệnh ngắn | Bí danh | Chức năng |
|---|---|---|
| `/loc [đk]` | `/screen` | Bộ lọc cổ phiếu toàn sàn — 3 bộ lọc dựng sẵn (Đột phá, Tích luỹ, Cảnh báo), hoặc gõ điều kiện tuỳ biến (VD: `/loc san=HOSE kn=MUA kl=1.2`) |
| `/tinhieu` | `/signals` | Tổng hợp cổ phiếu phát sinh tín hiệu MUA hoặc BÁN ở phiên gần nhất |
| `/market` | | Chỉ số thị trường VN-Index (điểm số, biến động tăng/giảm, biên độ ngày, thanh khoản) |
| `/tintuc` | `/news` | Tổng hợp tin tức vĩ mô, văn bản pháp quy, nghị định, nghị quyết mới nhất. Hỗ trợ `/tintuc on` (bật nhận tin tự động mỗi 1 giờ) và `/tintuc off` |

### ⭐ Nhóm 3: Quản lý danh mục & Cảnh báo cá nhân
| Lệnh ngắn | Bí danh | Chức năng |
|---|---|---|
| `/sub MA` | `/theodoi` | Thêm mã vào danh mục theo dõi cá nhân |
| `/watchlist` | `/danhsach` | Xem danh sách cổ phiếu theo dõi kèm trạng thái khuyến nghị hôm nay |
| `/unsub MA` | `/bosach` | Bỏ theo dõi một mã |
| `/canhbao` | `/alerts` | Bật/tắt cảnh báo tự động cuối phiên (15:05 mỗi ngày giao dịch) |
| `/trangthai` | `/status` | Tình trạng dữ liệu: kho giá, snapshot (mới/cũ/tạm thời), tiến độ nạp nền, lỗi gần nhất, RAM đang dùng |
| `/help` | `/start` | Menu hướng dẫn chi tiết và bàn phím tương tác nhanh |

`/loc` hỗ trợ các khoá lọc tuỳ chỉnh: `san` (sàn), `kn` (khuyến nghị tối
thiểu), `rsi` (vùng RSI), `may` (vị trí so với mây Kumo), `macd` (chiều giao
cắt), `phanky` (phân kỳ), `diem` (điểm tối thiểu), `kl` (tỷ lệ khối lượng tối
thiểu), `pe`/`roe` (chỉ khả dụng sau khi chạy `backfill_fundamentals.py`).
Công thức chi tiết ba bộ lọc dựng sẵn: [docs/cong-thuc.md](docs/cong-thuc.md).

---

## 5. Kiến trúc

Sơ đồ đầy đủ và nguyên tắc thiết kế: [docs/kien-truc.md](docs/kien-truc.md).
Công thức/ngưỡng của từng chỉ báo: [docs/cong-thuc.md](docs/cong-thuc.md).

```
Vietcap/DNSE --> data/market_store.py (kho giá TOÀN SÀN, 1 file parquet)
                        |  scripts/backfill_data.py (tải/cập nhật)
                        v
              analysis/snapshot.py (build_snapshot: recommend() 1 lần/mã,
                        |            chạy song song, ghi snapshot.parquet)
                        |  scripts/build_snapshot.py, hoặc tự động mỗi
                        |  phiên qua bot/scheduler.py (bot.scan_cron)
                        v
              analysis/screener.py, /tinhieu  --  CHỈ ĐỌC snapshot.parquet
                        |
                        v
                   bot/ (aiogram, polling)
```

Nguyên tắc hợp lưu quan trọng nhất: **Ichimoku có quyền phủ quyết khuyến
nghị MUA** khi giá nằm dưới mây Kumo, bất kể điểm tổng của MACD/RSI cao bao
nhiêu — xem `analysis/scoring.py`.

Mọi hàm nặng (tra cứu, khuyến nghị, vẽ biểu đồ, text mining BCTC, quét
watchlist) đều chạy qua `await asyncio.to_thread(...)` trong handler — bot
luôn trả lời `/help` ngay lập tức dù đang có lệnh nặng khác chạy song song
(xem `tests/test_nonblocking.py`).

---

## 6. Nguồn dữ liệu

| Loại dữ liệu | Nguồn chính | Nguồn dự phòng | Cần API key? |
|---|---|---|---|
| Giá lịch sử/cuối phiên (OHLCV) | DNSE OpenAPI (`data/dnse.py`) | Vietcap/VCI, endpoint công khai bảng giá (`data/vietcap.py`) | DNSE: có; Vietcap: không |
| Danh sách mã toàn sàn | DNSE (`/market/instruments`) | Vietcap (`/price/symbols/getAll`) | Không (Vietcap) |
| Báo cáo tài chính, chỉ số cơ bản | Vietcap/VCI qua `vnstock` | — | Không |
| Ngành (industry map) | Vietcap/VCI qua `vnstock` | — | Không |
| Tin tức công bố thông tin | Vietcap/VCI qua `vnstock` | — | Không |
| Realtime (khớp lệnh trực tiếp) | **Chưa cài** — `data/realtime.py` mới có giao diện + stub, mặc định tắt (`realtime.enabled: false`) | — | — |

`data/router.py` là nơi DUY NHẤT biết thứ tự ưu tiên nguồn — phần còn lại
của hệ thống chỉ gọi `get_router().ohlcv(...)` và không quan tâm dữ liệu đến
từ đâu. Khi nguồn lỗi/timeout/hết hạn mức, router tự chuyển sang nguồn dự
phòng theo thứ tự khai báo ở `config/settings.yaml: data.price_sources` /
`data.fundamental_sources`.

### Xử lý sự cố dữ liệu

| Tình huống | Hệ thống làm gì / bạn nên làm gì |
|---|---|
| Nguồn chính (DNSE) trả lỗi / timeout / chưa có API key | `data/router.py` tự chuyển sang nguồn dự phòng (Vietcap) |
| Bị giới hạn tần suất (429, hoặc vnstock/vnai tự gọi `sys.exit()` khi chạm hạn mức) | Lùi theo cấp số nhân tối đa 5 lần thử; nếu vẫn lỗi, đợi vài phút rồi chạy lại — bản Guest của vnstock giới hạn khoảng 20 lượt/phút |
| `backfill_data.py`/`backfill_fundamentals.py` báo hàng loạt mã lỗi hoặc trả về rỗng dù không có exception | Endpoint công khai của Vietcap **không chính thức**, có thể tạm thời giới hạn/chặn theo IP hoặc tần suất truy cập bất thường — thử lại sau vài phút; nếu chạy trên máy chủ/cloud ở nước ngoài, khả năng cao bị chặn nhiều hơn chạy từ máy cá nhân tại Việt Nam (xem mục 7) |
| Tất cả nguồn đều lỗi | Trả dữ liệu từ cache kèm nhãn thời điểm, bot **không** sập |
| Dữ liệu bẩn (BOM, CRLF, trùng lặp) | `data/cleaner.py` chuẩn hoá trước khi ghi cache |
| Mã không tồn tại / chưa đủ lịch sử | Handler bắt lỗi cụ thể, trả tin nhắn dễ hiểu qua `bot/formatters.py:error_card()` |
| Bot vừa khởi động trên máy trắng dữ liệu (lần đầu, hoặc Render gói Free vừa restart) | Bot tự dựng dữ liệu **tạm** cho danh sách theo dõi (`config/universe.yaml`, ~12 mã) trong vài giây — `/loc`, `/tinhieu` có kết quả ngay kèm ghi chú "Dữ liệu tạm thời" — rồi nạp toàn sàn ở nền (vài phút) |
| `/loc`, `/tinhieu` báo đang nạp hoặc báo lỗi | Thông báo nói rõ tiến độ (vd "450/1500 mã, khoảng 2 phút nữa") hoặc lỗi của lần nạp gần nhất. Gõ `/trangthai` để xem chi tiết |

---

## 7. Vận hành: Chạy ngầm không cần mở code & Triển khai 24/7

Bot dùng cơ chế **long polling** (`dispatcher.start_polling()`) — không cần mở port mạng, không cần cấu hình webhook hay SSL domain. Bạn có thể vận hành bot linh hoạt theo các cách dưới đây:

### 7.1. Chạy trên máy cá nhân (để thử / phát triển)

Bản chạy chính thức đặt trên Render (mục 7.3). Khi cần chạy thử trên máy:

```bash
python scripts/run_bot.py
```

Không cần đặt `PYTHONPATH` hay `pip install -e .` — script tự thêm `src/`
vào đường dẫn. Log hiện trên cửa sổ và ghi vào **`logs/bot.log`**; đóng cửa
sổ (hoặc `Ctrl+C`) là bot dừng.

> ⚠️ **Tạm dừng service trên Render trước khi chạy trên máy.** Hai tiến
> trình dùng chung một `TELEGRAM_BOT_TOKEN` sẽ tranh nhau nhận tin nhắn và
> Telegram báo lỗi xung đột (`Conflict: terminated by other getUpdates`).

**Cách kiểm tra bot còn sống:** gõ `/trangthai` trên Telegram (trả lời được
là bot đang chạy).

### 7.2. Chạy 24/7 vĩnh viễn trên Máy chủ Cloud / VPS Linux (Docker)

Nếu bạn muốn bot chạy liên tục cả ngày lẫn đêm kể cả khi bạn tắt máy tính cá nhân đi ngủ:

Dự án đã đóng gói sẵn `Dockerfile` và `docker-compose.yml`:

```bash
# 1. Clone code về VPS Linux (Ubuntu / Debian / CentOS)
git clone https://github.com/thienanpham160806-code/bot-phan-tich.git
cd bot-phan-tich

# 2. Cấu hình biến môi trường
cp .env.example .env
nano .env  # Điền TELEGRAM_BOT_TOKEN

# 3. Khởi động bot chạy nền vĩnh viễn bằng Docker
docker compose up -d --build

# Xem log hoạt động:
docker compose logs -f
```

### 7.3. Triển khai trên Render.com — giới hạn thực tế và lựa chọn

**Giới hạn của gói Free (đã gặp thực tế khi deploy):**

- **512 MB RAM, CPU chia sẻ.** Riêng việc nạp thư viện của bot (aiogram,
  pandas, vnstock) đã chiếm khoảng 250–300 MB, chỉ còn khoảng 200 MB cho
  dữ liệu. Toàn sàn vẫn chạy được nhưng sát giới hạn; vượt là container bị
  tắt và khởi động lại.
- **Không có ổ đĩa lưu bền.** Mọi thứ trong `data/` (kho giá, snapshot,
  danh sách theo dõi, cài đặt cảnh báo của người dùng) **mất sạch mỗi lần
  container khởi động lại** (deploy mới, lỗi, hoặc Render tự khởi động lại).
  Mỗi lần như vậy bot phải nạp lại kho giá từ đầu: vài giây đầu chỉ có dữ
  liệu tạm cho danh sách theo dõi, vài phút sau mới có đủ vũ trụ.
- **Tự ngủ sau ~15 phút không có request HTTP.** Bot chỉ polling Telegram
  ra ngoài, không ai gọi HTTP vào, nên nếu không có dịch vụ ping thì cả
  tiến trình bị dừng (kể cả lịch quét 15:05).
- **Không có Background Worker** (loại phù hợp đúng bản chất bot polling,
  không bị quét port). Gói Free báo *"service type is not available for
  this plan"*, nên phải chạy dưới dạng Web Service kèm health-check HTTP
  giả trong `bot/main.py`.

**Ba lựa chọn:**

| | Lựa chọn | Dữ liệu | Chi phí | Hợp khi |
|---|---|---|---|---|
| **(a)** | **Chạy trên máy cá nhân** (mục 7.1) | Đầy đủ toàn sàn, giữ được qua các lần tắt/mở | Miễn phí | **Demo, chấm bài** — nhanh nhất, ổn định nhất |
| (b) | Render gói trả phí + **Persistent Disk** | Đầy đủ, không mất khi restart | Trả phí hàng tháng | Cần chạy 24/7 lâu dài |
| (c) | Render Free + vũ trụ rút gọn 300 mã + UptimeRobot | Rút gọn, nạp lại mỗi lần restart | Miễn phí | Muốn bot online 24/7 mà không trả phí, chấp nhận hạn chế |

**Khuyến nghị: dùng (a) khi demo và chấm bài.** Chạy `python scripts/run_bot.py`
trên máy cá nhân sau khi đã chạy `scripts/backfill_data.py` và
`scripts/build_snapshot.py` — có ngay dữ liệu toàn sàn, `/loc` trả lời tức
thì. (c) chỉ là phương án dự phòng "cho bot luôn online", không nên dùng để
trình diễn trước hội đồng vì có thể đúng lúc đó container vừa restart và
đang nạp lại dữ liệu.

**Cách làm (b):** nâng service lên gói trả phí → đổi `render.yaml` sang
`type: worker` (không cần health-check/UptimeRobot) → thêm Persistent Disk
gắn vào `/app/data` (thư mục `DATA_DIR` mặc định trong Docker image) →
deploy lại. Bỏ các biến giới hạn quy mô ở (c) để chạy toàn sàn.

**Cách làm (c):**

1. Render → **New +** → **Blueprint** → chọn repo này, nhánh `main` —
   `render.yaml` đã đặt sẵn `UNIVERSE_MAX_SYMBOLS=300`, `MARKET_COUNT_BACK=400`,
   `SNAPSHOT_MAX_WORKERS=1`. **Nếu service được tạo thủ công** (New + →
   Web Service, không qua Blueprint) thì `render.yaml` **không tự áp dụng**:
   phải tự thêm ba biến này trong tab **Environment** của service.
2. Điền `TELEGRAM_BOT_TOKEN` → Deploy.
3. UptimeRobot (miễn phí) → **Add New Monitor** → HTTP(s) →
   `https://<ten-service>.onrender.com/healthz` → Interval **5 phút**.
4. Kiểm tra trên Telegram: `/trangthai` (kho giá, snapshot, tiến độ nạp,
   lỗi gần nhất, RAM) và `/trangthai chandoan` (RAM/CPU thật của container,
   có gọi được Vietcap/DNSE không — gói Free không có Shell nên đây là cách
   chẩn đoán duy nhất). Trên máy cá nhân chạy `python scripts/diagnose.py`.

### 7.4. Lịch chạy tự động của Bot

Hệ thống được điều phối tự động bởi `APScheduler`:

1. **Lịch quét tín hiệu cuối phiên (`bot.scan_cron`, mặc định `15:05` thứ 2 – thứ 6):**
   - Tự động cập nhật nến phiên hôm nay và tính snapshot chỉ báo kỹ thuật toàn sàn.
   - Quét danh mục cổ phiếu mà từng người dùng đang theo dõi (`/sub`) và chủ động gửi cảnh báo tín hiệu MUA/BÁN hoặc vi phạm cắt lỗ.
   - Hỗ trợ chạy bù trong vòng 1 tiếng (`misfire_grace_time=3600s`) nếu bot khởi động trễ.
2. **Lịch tổng hợp tin tức vĩ mô & pháp luật (`bot.news_cron`, mặc định mỗi 1 giờ từ `08:00 – 22:00`):**
   - Tự động quét RSS từ CafeF & VnExpress, phân loại thông minh (Chính sách, Nghị định, Vĩ mô, TTCK).
   - Tự động phát sóng (broadcast) bản tin tổng hợp tới tất cả người dùng bật chế độ nhận tin (`/tintuc on`).
   - Chỉ gửi tin đăng trong 2 giờ gần nhất; nguồn "CafeF Vĩ mô" lẫn tin xã hội nên chỉ giữ tin khớp từ khoá chính sách/vĩ mô.
> ⚠️ **Render gói Free mất đăng ký sau mỗi lần khởi động lại.** Người đăng ký
> `/tintuc on` và danh mục `/sub` nằm trong SQLite ở `data/`, mà gói Free xoá
> sạch thư mục này mỗi lần deploy/restart. Giữ đăng ký bản tin cố định không
> cần dịch vụ ngoài: đặt biến **`AUTO_SUBSCRIBE_CHAT_IDS`** (các chat id, cách
> nhau dấu phẩy; `/tintuc on` in ra chat id của bạn) trong tab Environment —
> mỗi lần khởi động bot tự bật lại bản tin cho các chat này.

---

## 8. Giấy phép thư viện

Dự án dùng cho mục đích học tập. Lưu ý điều khoản của một số thư viện:

- `vnstock` — giấy phép tuỳ chỉnh, miễn phí cho mục đích cá nhân, dùng thương mại cần xin phép tác giả.
- DNSE LightSpeed API — có ràng buộc về việc phân phối lại dữ liệu, đọc kỹ điều khoản dịch vụ trước khi public repo.

---

## 9. Miễn trừ trách nhiệm

Đây là sản phẩm học thuật. Mọi tín hiệu do bot sinh ra **không phải** khuyến nghị đầu tư.
