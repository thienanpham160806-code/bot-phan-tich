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

Ba bước theo đúng thứ tự — **bắt buộc** phải chạy bước 1 và 2 trước khi mở
bot lần đầu, nếu không `/loc` và `/tinhieu` sẽ báo "đang chuẩn bị dữ liệu":

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
| `/tintuc` | `/news` | **Mới:** Tổng hợp tin tức vĩ mô, văn bản pháp quy, nghị định, nghị quyết mới nhất. Hỗ trợ `/tintuc on` (bật nhận tin tự động mỗi 1 giờ) và `/tintuc off` |

### ⭐ Nhóm 3: Quản lý danh mục & Cảnh báo cá nhân
| Lệnh ngắn | Bí danh | Chức năng |
|---|---|---|
| `/sub MA` | `/theodoi` | Thêm mã vào danh mục theo dõi cá nhân |
| `/watchlist` | `/danhsach` | Xem danh sách cổ phiếu theo dõi kèm trạng thái khuyến nghị hôm nay |
| `/unsub MA` | `/bosach` | Bỏ theo dõi một mã |
| `/canhbao` | `/alerts` | Bật/tắt cảnh báo tự động cuối phiên (15:05 mỗi ngày giao dịch) |
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
| `/loc`, `/tinhieu` báo "đang chuẩn bị dữ liệu" | Chưa chạy `backfill_data.py`/`build_snapshot.py` lần nào, hoặc bot vừa khởi động và đang tự cập nhật ở nền (`ensure_fresh_in_background()`) — đợi vài phút rồi thử lại |

---

## 7. Vận hành: Chạy ngầm không cần mở code & Triển khai 24/7

Bot dùng cơ chế **long polling** (`dispatcher.start_polling()`) — không cần mở port mạng, không cần cấu hình webhook hay SSL domain. Bạn có thể vận hành bot linh hoạt theo các cách dưới đây:

### 7.1. Chạy ngầm trên Windows (Không cần mở VS Code / Antigravity)

Trong thư mục gốc dự án đã chuẩn bị sẵn các công cụ 1-click:

- **`chay_bot_an.bat`** *(Khuyên dùng)*: Click đúp vào file này, bot sẽ tự động khởi động chạy ngầm dưới nền hệ thống bằng `pythonw.exe` (không hiện bất kỳ cửa sổ dòng lệnh đen nào). **Bạn có thể tắt hoàn toàn VS Code / Antigravity / Terminal, bot vẫn tiếp tục hoạt động trên Telegram!**
- **`tat_bot.bat`**: Click đúp để dừng toàn bộ tiến trình bot đang chạy ngầm khi muốn tắt hoặc cập nhật code.
- **`chay_bot_hien_log.bat`**: Dùng khi bạn muốn mở cửa sổ console đen để vừa xem trực tiếp từng dòng log xử lý của bot vừa kiểm tra.

> 💡 **Tự động chạy mỗi khi bật máy tính:**
> 1. Nhấn tổ hợp phím `Windows + R` ➔ gõ `shell:startup` rồi bấm Enter (thư mục Startup của Windows sẽ mở ra).
> 2. Nhấp chuột phải vào `chay_bot_an.bat` ➔ chọn *Show more options* ➔ *Create shortcut* (Tạo lối tắt).
> 3. Kéo shortcut vừa tạo thả vào thư mục Startup.
> ➔ Từ nay cứ mở máy tính lên là bot tự động chạy ngầm, không cần thao tác thủ công.

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

### 7.3. Triển khai trên Render.com (gói Free)

Bot polling Telegram về bản chất hợp với loại **Background Worker** (không
mở port, không bị quét port) — nhưng **gói Free của Render KHÔNG hỗ trợ
Background Worker** (chỉ trả phí từ gói Starter trở lên mới tạo được loại
này — lỗi gặp thực tế: *"service type is not available for this plan"*).
Nên trên gói Free, `render.yaml` khai báo **`type: web`**, kèm một HTTP
health-check dự phòng trong `bot/main.py` (bắt biến `PORT` Render tự cấp,
mở một server trả `200 OK`) để bot qua được vòng quét port của Render.

**Deploy:** Render dashboard → **New +** → **Blueprint** (hoặc **Web
Service** thủ công, chọn Docker runtime) → chọn repo này, nhánh `main` →
điền `TELEGRAM_BOT_TOKEN` → Deploy.

**Giới hạn quy mô cho vừa 512 MB RAM** (tuỳ chọn, đặt ở mục Environment
của service, không cần sửa file trong repo):

| Biến | Ý nghĩa | Gợi ý cho Render Free |
|---|---|---|
| `UNIVERSE_MAX_SYMBOLS` | Chỉ tính snapshot cho N mã thanh khoản nhất (0 = không giới hạn) | `400` |
| `MARKET_COUNT_BACK` | Số phiên tải cho mỗi mã khi nạp kho lần đầu (mặc định 500) | để trống |

Đo RAM trước khi deploy: `python scripts/bench_snapshot.py` (in thời gian
và RAM đỉnh khi dựng snapshot).

**Vấn đề còn lại — BẮT BUỘC phải xử lý:** gói Free của Render tự "ngủ"
(spin down) sau **~15 phút không có request HTTP nào gọi đến** service.
Sẽ không có ai tự gọi HTTP vào bot cả (bot chỉ polling Telegram RA NGOÀI,
không nhận request từ ai) — nên nếu không làm gì thêm, khoảng 15 phút sau
khi deploy, **cả tiến trình bot sẽ bị dừng hẳn** (kể cả vòng polling
Telegram, kể cả lịch quét 15h05/tin tức hàng giờ), và không tự chạy lại
được cho tới khi có ai đó gọi lại URL hoặc redeploy thủ công.

**Cách giữ bot luôn thức, miễn phí:** dùng một dịch vụ ping định kỳ bên
ngoài gọi vào endpoint health-check mỗi 5–10 phút, ví dụ
[UptimeRobot](https://uptimerobot.com) (miễn phí):

1. Lấy URL public của service trên Render (dạng
   `https://<ten-service>.onrender.com`), thêm `/healthz` vào cuối.
2. UptimeRobot → **Add New Monitor** → Monitor Type: **HTTP(s)** → dán URL
   trên → Monitoring Interval: **5 phút** → Save.
3. Từ đó UptimeRobot tự gọi vào bot mỗi 5 phút, Render luôn thấy có
   "traffic" nên không bao giờ spin down.

Nếu sau này nâng cấp lên gói trả phí, chỉ cần đổi `render.yaml` sang
`type: worker` và tạo lại service qua Blueprint — không cần cấu hình
health-check/ping ngoài nữa.

### 7.4. Lịch chạy tự động của Bot

Hệ thống được điều phối tự động bởi `APScheduler`:

1. **Lịch quét tín hiệu cuối phiên (`bot.scan_cron`, mặc định `15:05` thứ 2 – thứ 6):**
   - Tự động cập nhật nến phiên hôm nay và tính snapshot chỉ báo kỹ thuật toàn sàn.
   - Quét danh mục cổ phiếu mà từng người dùng đang theo dõi (`/sub`) và chủ động gửi cảnh báo tín hiệu MUA/BÁN hoặc vi phạm cắt lỗ.
   - Hỗ trợ chạy bù trong vòng 1 tiếng (`misfire_grace_time=3600s`) nếu bot khởi động trễ.
2. **Lịch tổng hợp tin tức vĩ mô & pháp luật (`bot.news_cron`, mặc định mỗi 1 giờ từ `08:00 – 22:00`):**
   - Tự động quét RSS từ CafeF & VnExpress, phân loại thông minh (Chính sách, Nghị định, Vĩ mô, TTCK).
   - Tự động phát sóng (broadcast) bản tin tổng hợp tới tất cả người dùng bật chế độ nhận tin (`/tintuc on`).

---

## 8. Giấy phép thư viện

Dự án dùng cho mục đích học tập. Lưu ý điều khoản của một số thư viện:

- `vnstock` — giấy phép tuỳ chỉnh, miễn phí cho mục đích cá nhân, dùng thương mại cần xin phép tác giả.
- DNSE LightSpeed API — có ràng buộc về việc phân phối lại dữ liệu, đọc kỹ điều khoản dịch vụ trước khi public repo.

---

## 9. Miễn trừ trách nhiệm

Đây là sản phẩm học thuật. Mọi tín hiệu do bot sinh ra **không phải** khuyến nghị đầu tư.
