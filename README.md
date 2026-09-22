# bot-phan-tich

Telegram Bot phân tích kỹ thuật chứng khoán Việt Nam — hợp lưu ba hệ chỉ báo
**MACD, RSI (ngưỡng thích ứng), Ichimoku Kinko Hyo**.

Nguồn dữ liệu: **DNSE OpenAPI** (giá cuối phiên, danh sách mã — nguồn chính,
đã test sống) và **Vietcap/VCI** qua `vnstock` (báo cáo tài chính, danh sách
mã, ngành — nguồn dự phòng). Realtime (WebSocket/MQTT streaming) là tính
năng **riêng, chưa cài** (`data/realtime.py` mới có giao diện + stub) — xem
mục [Cấu hình nguồn dữ liệu](#cấu-hình-nguồn-dữ-liệu-dnse--vietcap) bên
dưới; bot chạy đầy đủ bằng dữ liệu cuối phiên trong lúc chờ.

---

## 1. Năm nhóm chức năng

| Nhóm | Lệnh chính | Module |
|---|---|---|
| Tra cứu mã cổ phiếu | `/tracuu` | `analysis/lookup.py` |
| Khuyến nghị mua/bán | `/khuyennghi`, `/bieudo` | `analysis/scoring.py` |
| Lọc cổ phiếu | `/loc` | `analysis/screener.py` |
| Bình luận tình hình tài chính (text mining BCTC) | `/bctc` | `analysis/fintext.py` |
| Cảnh báo tự động cuối phiên | `/canhbao`, `/danhsach` | `alerts/eod.py` |

Chi tiết công thức: [`docs/cong-thuc.md`](docs/cong-thuc.md). Sơ đồ kiến
trúc: [`docs/kien-truc.md`](docs/kien-truc.md).

### Kiến trúc rút gọn

```
data/ (router, cache, DNSE/Vietcap, realtime STUB)
  -> indicators/ (MACD, RSI, Ichimoku, phân kỳ — tự cài bằng pandas/numpy)
    -> analysis/ (scoring, lookup, screener, fintext)
      -> alerts/ (watchlist, quét cuối phiên)  |  risk/ (sizing, stops)
        -> backtest/ (engine, metrics, walk_forward, signals)
        -> bot/ (aiogram: handlers, charts, formatters, scheduler)
```

Nguyên tắc hợp lưu quan trọng nhất: **Ichimoku có quyền phủ quyết khuyến
nghị MUA** khi giá nằm dưới mây Kumo, bất kể điểm tổng của MACD/RSI cao bao
nhiêu — xem `analysis/scoring.py`.

---

## 2. Cài đặt

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

Mở `.env` và điền:

| Biến | Lấy ở đâu |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Chat với [@BotFather](https://t.me/BotFather) trên Telegram, lệnh `/newbot` |
| `DNSE_API_KEY`, `DNSE_API_SECRET` | EntradeX → mục LightSpeed API (xem hướng dẫn bên dưới) |
| `VNSTOCK_ACCEPT_TOS` | Đặt `1` sau khi chạy `register_user()` của vnstock một lần |

> **Không bao giờ** commit file `.env`. File này đã nằm trong `.gitignore`
> (chỉ `.env.example` — bản mẫu rỗng — mới được commit). Chưa có
> `DNSE_API_KEY`/`DNSE_API_SECRET` cũng không sao — `data/router.py` tự động
> dùng nguồn dự phòng (Vietcap/VCI qua `vnstock`, không cần API key) nên bot
> vẫn chạy được đầy đủ phần dữ liệu cuối phiên trong lúc chờ.

### Cấu hình nguồn dữ liệu (DNSE / Vietcap)

**DNSE (nguồn chính, cần tài khoản chứng khoán DNSE dạng `064Cxxxxxx`):**

1. Mở tài khoản online tại <https://www.dnse.com.vn> (eKYC bằng CCCD gắn
   chip), không cần nạp tiền để dùng phần dữ liệu thị trường.
2. Đăng nhập **EntradeX** (<https://banggia.dnse.com.vn> hoặc app EntradeX)
   → mục **LightSpeed API** trong cài đặt tài khoản → tạo khoá.
3. **API secret chỉ hiện đúng một lần** — copy ngay vào `.env`, lỡ mất phải
   tạo khoá mới. Không thấy mục LightSpeed API thì liên hệ DNSE (hotline
   024 7108 9234 / hello@dnse.com.vn), cung cấp số tài khoản 064C + họ tên.
4. `pip install openapi-sdk` (theo docs của DNSE) **không cài được** — tên
   gói đó chỉ là ví dụ trong docs, không phải tên thật trên PyPI. Tên gói
   PyPI thật là `dnse-sdk-openapi` (đã có sẵn trong `requirements.txt`,
   không cần cài riêng — xem `data/dnse.py`).

**Vietcap (nguồn dự phòng, không cần API key):** qua thư viện `vnstock`
(`pip install -U vnstock`, chạy `register_user()` một lần, đặt
`VNSTOCK_ACCEPT_TOS=1`). Có giới hạn tần suất (~20 lượt/phút bản miễn phí)
nên mọi nơi trong bot đều gọi qua `data/router.py` (đã có cache), không gọi
thẳng vnstock trong handler.

> Lỡ commit lộ `DNSE_API_KEY`/`DNSE_API_SECRET` lên Git: vào EntradeX **tạo
> khoá mới ngay** (khoá cũ coi như đã lộ) rồi mới dọn lịch sử commit — đổi
> khoá trước, dọn git sau.

---

## 3. Chạy

```bash
python scripts/init_db.py                  # tạo bảng SQLite
python scripts/backfill_data.py --years 3  # tải lịch sử giá + BCTC vào cache
python -m bot_phan_tich.bot.main           # chạy bot
```

Kiểm thử: `pytest -q`. Chất lượng mã: `ruff check src tests`.

Trên Windows có thể dùng script tác vụ cho gọn:

```powershell
.\tasks.ps1 install
.\tasks.ps1 test
.\tasks.ps1 bot
```

---

## 4. Bộ lệnh bot

Mỗi lệnh có cả bí danh tiếng Việt và tiếng Anh.

| Lệnh | Bí danh | Chức năng |
|---|---|---|
| `/tracuu MA` | `/info` | Hồ sơ + chỉ số chính + cập nhật gần đây |
| `/khuyennghi MA` | `/rec`, `/kn` | Khuyến nghị, điểm ba hệ, vùng giá vào/cắt lỗ/mục tiêu, ba lý do |
| `/bieudo MA` | `/chart` | Biểu đồ nến kèm mây Ichimoku, MACD, RSI |
| `/loc` | `/screen` | Lọc cổ phiếu, có nút bấm cho ba bộ lọc dựng sẵn (đột phá/tích luỹ/cảnh báo) |
| `/bctc MA` | `/fin` | Bình luận tình hình tài chính từ text mining (gửi kèm PDF BCTC nếu có) |
| `/theodoi MA` | `/sub` | Thêm vào danh sách theo dõi |
| `/bosach MA` | `/unsub` | Bỏ theo dõi |
| `/danhsach` | `/watchlist` | Xem danh sách theo dõi kèm khuyến nghị hiện tại |
| `/canhbao` | `/alerts` | Bật/tắt cảnh báo tự động cuối phiên |
| `/market` | | Trạng thái chỉ số tham chiếu (VNINDEX) |
| `/help` | `/start` | Hướng dẫn + menu nút bấm |

---

## 5. Xử lý sự cố dữ liệu

| Tình huống | Hệ thống làm gì |
|---|---|
| Nguồn chính (DNSE) trả lỗi / timeout / chưa có API key | `data/router.py` tự chuyển sang nguồn dự phòng (Vietcap) theo thứ tự khai báo trong `config/settings.yaml` |
| Bị giới hạn tần suất (429) | Lùi theo cấp số nhân, tối đa 5 lần thử, có nhiễu ngẫu nhiên |
| Tất cả nguồn đều lỗi | Trả dữ liệu từ cache kèm nhãn thời điểm, bot **không** sập |
| Dữ liệu bẩn (BOM, CRLF, trùng lặp) | `data/cleaner.py` chuẩn hoá trước khi ghi cache |
| Mã không tồn tại / chưa đủ lịch sử | Handler bắt lỗi cụ thể, trả tin nhắn dễ hiểu qua `bot/formatters.py:error_card()` |
| Realtime chưa cài (`realtime.enabled: false`) | Toàn bộ bot chạy bằng dữ liệu cuối phiên — không đường code nào bắt buộc phải có realtime |

---

## 6. Giấy phép thư viện

Dự án dùng cho mục đích học tập. Lưu ý điều khoản của một số thư viện:

- `vnstock` — giấy phép tuỳ chỉnh, miễn phí cho mục đích cá nhân, dùng thương mại cần xin phép tác giả.
- DNSE LightSpeed API — có ràng buộc về việc phân phối lại dữ liệu, đọc kỹ điều khoản dịch vụ trước khi public repo.

---

## 7. Miễn trừ trách nhiệm

Đây là sản phẩm học thuật. Mọi tín hiệu do bot sinh ra **không phải** khuyến nghị đầu tư.
