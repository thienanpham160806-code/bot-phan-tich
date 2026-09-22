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
#    Lần đầu tải ~750 phiên (~3 năm)/mã cho ~1.500 mã — mất khoảng 2-3 phút
#    (đo thực tế: 1.523 mã trong 123 giây), tuỳ tốc độ mạng. Các lần sau chỉ
#    tải thêm vài phiên mới nhất và gộp vào kho cũ — vài chục giây.
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

Mỗi lệnh có cả bí danh tiếng Việt và tiếng Anh.

| Lệnh | Bí danh | Chức năng |
|---|---|---|
| `/tracuu MA` | `/info` | Hồ sơ + chỉ số chính + tin tức gần đây |
| `/khuyennghi MA` | `/rec`, `/kn` | Khuyến nghị, điểm ba hệ, vùng giá vào/cắt lỗ/mục tiêu, lý do |
| `/bieudo MA` | `/chart` | Biểu đồ nến kèm mây Ichimoku, MACD, RSI |
| `/loc [điều kiện]` | `/screen` | Lọc cổ phiếu — 3 bộ lọc dựng sẵn (đột phá/tích luỹ/cảnh báo), hoặc tự gõ vd `/loc san=HOSE kn=MUA rsi=quaban` |
| `/tinhieu` | `/signals` | Tín hiệu MUA/TÍCH LUỸ và BÁN/GIẢM TỶ TRỌNG của phiên gần nhất |
| `/bctc MA` | `/fin` | Bình luận tình hình tài chính từ text mining (gửi kèm PDF BCTC nếu có) |
| `/theodoi MA` | `/sub` | Thêm vào danh sách theo dõi |
| `/bosach MA` | `/unsub` | Bỏ theo dõi |
| `/danhsach` | `/watchlist` | Xem danh sách theo dõi kèm khuyến nghị hiện tại |
| `/canhbao` | `/alerts` | Bật/tắt cảnh báo tự động cuối phiên |
| `/market` | | Trạng thái chỉ số tham chiếu (VNINDEX) |
| `/help` | `/start` | Hướng dẫn + menu nút bấm |

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

## 7. Vận hành: polling trên máy cá nhân, không cần server

Bot dùng **long polling** (`dispatcher.start_polling()`, `bot/main.py`) —
không mở port, không cần webhook, không cần domain/SSL, không cần thuê
server. Chạy `python -m bot_phan_tich.bot.main` trên máy cá nhân (kể cả
Windows) là đủ; bot vẫn nhận và trả lời tin nhắn Telegram bình thường miễn
máy đang bật và có mạng.

**Cảnh báo tự động cuối phiên chỉ bắn nếu bot đang chạy quanh giờ quét**
(`config/settings.yaml: bot.scan_cron`, mặc định `5 15 * * 1-5` = **15:05**
các ngày làm việc, giờ Việt Nam). Cụ thể:

- Nếu bot đang chạy đúng 15:05 → quét + gửi cảnh báo ngay.
- Nếu bot khởi động **trong vòng 1 tiếng sau** 15:05 (đến 16:05) → APScheduler
  tự chạy bù công việc bị lỡ (`misfire_grace_time=3600` giây).
- Nếu bot **tắt hẳn** qua khung giờ đó (ví dụ tắt máy qua đêm) → không có
  cảnh báo Telegram tự động cho phiên đó. Snapshot vẫn tự cập nhật ở nền vào
  lần khởi động kế tiếp (`ensure_fresh_in_background()`), nên `/loc`/`/tinhieu`
  vẫn cho kết quả đúng của phiên gần nhất, chỉ là không có tin nhắn chủ động.

Vì vậy: muốn nhận cảnh báo tự động đều đặn, hãy để máy/bot chạy xuyên suốt
khung 15:00–16:00 các ngày giao dịch (hoặc triển khai trên một máy luôn bật
— `Dockerfile`/`docker-compose.yml` có sẵn nếu muốn chạy như một service).

---

## 8. Giấy phép thư viện

Dự án dùng cho mục đích học tập. Lưu ý điều khoản của một số thư viện:

- `vnstock` — giấy phép tuỳ chỉnh, miễn phí cho mục đích cá nhân, dùng thương mại cần xin phép tác giả.
- DNSE LightSpeed API — có ràng buộc về việc phân phối lại dữ liệu, đọc kỹ điều khoản dịch vụ trước khi public repo.

---

## 9. Miễn trừ trách nhiệm

Đây là sản phẩm học thuật. Mọi tín hiệu do bot sinh ra **không phải** khuyến nghị đầu tư.
