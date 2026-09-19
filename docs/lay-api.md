# Hướng dẫn lấy API: DNSE và Vietcap

> Cập nhật: 19/09/2026. Quy trình của công ty chứng khoán có thể đổi — nếu màn hình khác mô tả dưới đây thì hỏi CSKH, đừng đoán.

---

## 1. DNSE — LightSpeed API (nguồn chính)

### 1.1. Điều kiện bắt buộc

Phải có **tài khoản chứng khoán DNSE** (số tài khoản dạng `064Cxxxxxx`). Không có tài khoản thì không có API — đây là điều kiện cứng, không lách được.

Mở tài khoản online tại <https://www.dnse.com.vn>, eKYC bằng CCCD gắn chip, thường xong trong ngày. **Không cần nạp tiền** để dùng phần dữ liệu thị trường.

> Lưu ý từ tài liệu DNSE: khi đăng ký **đừng dùng tài khoản Gmail/Google để đăng nhập** — đăng ký bằng số điện thoại/email thường, nếu không phần API sẽ vướng.

### 1.2. Các bước lấy API key và secret

1. Đăng nhập **EntradeX** (nền tảng web của DNSE): <https://banggia.dnse.com.vn> hoặc app EntradeX.
2. Vào mục **LightSpeed API** trong phần cài đặt/tiện ích của tài khoản.
3. Bấm tạo khoá → hệ thống sinh ra **API key** và **API secret**.
4. **API secret chỉ hiện đúng một lần.** Copy ngay và dán vào `.env`. Lỡ mất thì phải tạo khoá mới, không xem lại được.
5. Dán vào file `.env` trong repo:

```
DNSE_API_KEY=...
DNSE_API_SECRET=...
DNSE_BASE_URL=https://openapi.dnse.com.vn
```

### 1.3. Nếu không thấy mục LightSpeed API

Dịch vụ có thể chưa được kích hoạt cho tài khoản. Liên hệ DNSE, cung cấp **số tài khoản 064C + họ tên**:

- Hotline: **024 7108 9234**
- Email: **hello@dnse.com.vn**
- Zalo / Facebook: tìm "DNSE"

Khách hàng cá nhân thường đăng ký online được ngay; khách hàng tổ chức mới phải ký hợp đồng giấy. Nhóm mình là cá nhân nên đi đường online.

### 1.4. Cài SDK và kiểm tra

```bash
pip install openapi-sdk
```

Script kiểm tra nhanh — chạy cái này **trước khi** làm gì tiếp:

```python
import os
from dotenv import load_dotenv
from dnse import DNSEClient

load_dotenv()
client = DNSEClient(
    api_key=os.getenv("DNSE_API_KEY"),
    api_secret=os.getenv("DNSE_API_SECRET"),
    base_url="https://openapi.dnse.com.vn",
)

# In ra toàn bộ phương thức SDK đang có — tên hàm có thể khác giữa các phiên bản
print([m for m in dir(client) if not m.startswith("_")])

# Thử một lệnh đọc, dry_run để xem request mà không gọi mạng thật
print(client.get_accounts(dry_run=True))
```

**Gửi tui output của dòng `print([m for m in dir(client)...])`** — tui cần biết tên hàm thật để sửa `data/dnse.py` cho khớp.

### 1.5. Cần biết thêm

- Có hai lớp khác nhau: **Market Data API** (dữ liệu, chỉ cần key/secret) và **Trading API** (đặt lệnh, cần thêm OTP email + trading token). **Đồ án chỉ cần Market Data** — đừng đụng vào phần đặt lệnh, vừa rủi ro vừa không có trong đề.
- Giới hạn tài liệu ghi là tối đa **2.000 mã đồng thời** cho luồng realtime. Thừa sức cho đồ án.
- Realtime đi qua **WebSocket/MQTT**, không phải REST. Dữ liệu lịch sử (OHLC) mới là REST.
- Điều khoản dịch vụ LightSpeed API có ràng buộc về việc phân phối lại dữ liệu. Đọc lướt một lượt trước khi public repo, và **ghi rõ trong README là dùng cho mục đích học tập**.

---

## 2. Vietcap — nguồn dự phòng

### 2.1. Sự thật cần biết trước

**Vietcap không có cổng đăng ký API công khai cho nhà đầu tư cá nhân.** Không có trang developer, không có nơi bấm nút lấy key như DNSE. Đừng mất thời gian tìm.

Thực tế có ba đường, xếp theo mức khuyến nghị:

### 2.2. Đường A — qua thư viện `vnstock` (khuyến nghị)

`vnstock` đã bọc sẵn nguồn VCI (Vietcap) và chuẩn hoá tên cột báo cáo tài chính — đây là phần tốn công nhất nếu tự làm.

```bash
pip install -U vnstock
```

```python
from vnstock import register_user
register_user()      # chạy đúng một lần, làm theo hướng dẫn hiện ra
```

Sau đó đặt `VNSTOCK_ACCEPT_TOS=1` trong `.env`.

- **Không cần API key.**
- Có giới hạn tần suất gọi (bản miễn phí khoảng 20 lượt/phút). Vì vậy repo đã có cache — **luôn gọi qua `data/router.py`**, đừng gọi thẳng vnstock trong handler của bot.
- Giấy phép của vnstock là **tuỳ chỉnh**: miễn phí cho mục đích cá nhân/học tập, dùng thương mại phải xin phép tác giả. Ghi dòng này vào README.

### 2.3. Đường B — gọi thẳng endpoint nội bộ của Vietcap

Trang `trading.vietcap.com.vn` có các endpoint nội bộ mà trình duyệt vẫn gọi (ví dụ `chart/OHLCChart/gap-chart`, `data-mt/graphql`). Không có tài liệu, không cam kết ổn định, **có thể đổi hoặc chặn bất cứ lúc nào**.

Chỉ dùng khi đường A hỏng, và phải bọc trong try/except để không kéo sập bot. Không đưa vào đường ra quyết định chính.

### 2.4. Đường C — liên hệ Vietcap

Nếu nhóm muốn có nguồn chính thức: mở tài khoản tại Vietcap rồi hỏi CSKH về kết nối dữ liệu. Khả năng cao họ chỉ cấp cho tổ chức. **Đừng chặn tiến độ đồ án để chờ cái này.**

---

## 3. Thứ tự nên làm

| Bước | Việc | Thời gian ước tính |
|---|---|---|
| 1 | Mở tài khoản DNSE, eKYC | 1 buổi |
| 2 | Lấy API key/secret trên EntradeX, điền `.env` | 15 phút |
| 3 | Chạy script kiểm tra ở mục 1.4, gửi output cho nhóm | 10 phút |
| 4 | `pip install -U vnstock` + `register_user()` | 10 phút |
| 5 | Chạy `python scripts/backfill_data.py --years 3` | 10–30 phút |

**Trong lúc chờ bước 1**, nhóm vẫn code được bình thường: `data/router.py` có nguồn dự phòng nên chỉ cần vnstock là đã chạy được toàn bộ phần lịch sử. Phần realtime để sau, và prompt refactor đã chừa sẵn chỗ cho nó.

---

## 4. An toàn

- `.env` đã nằm trong `.gitignore`. **Kiểm tra lại bằng `git status` trước mỗi lần commit** — repo đang public.
- Nếu lỡ commit key lên GitHub: vào EntradeX **tạo khoá mới ngay** (khoá cũ coi như đã lộ), rồi mới xoá lịch sử commit. Đổi khoá trước, dọn git sau.
- Không dùng API key vào phần đặt lệnh. Đồ án chỉ đọc dữ liệu.
