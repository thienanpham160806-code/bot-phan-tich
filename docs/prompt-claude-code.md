# Prompt cho Claude Code — refactor repo `bot-phan-tich`

> Cách dùng: mở terminal tại thư mục `bot-phan-tich`, chạy `claude`, rồi dán **toàn bộ** phần trong khung dưới đây (từ dòng "Bối cảnh" đến hết).
> Nếu Claude Code hỏi xác nhận trước khi xoá file, cứ đồng ý — phần cần giữ đã được liệt kê rõ.

---

Bối cảnh: đây là repo đồ án môn học — một Telegram bot tín hiệu đầu tư chứng khoán Việt Nam. Repo hiện đang chứa một khung cũ xây theo hướng "phễu lọc 5 tầng" gồm bộ lọc chế độ thị trường bằng HMM, chấm điểm cơ bản Piotroski/Beneish/Altman, xếp hạng RS, mẫu hình VCP và một lớp học máy meta-labeling. **Nhóm đã họp và đổi hướng.** Nhiệm vụ của bạn là refactor repo sang hướng mới, không phải viết lại từ đầu.

Hãy đọc `README.md`, `docs/kien-truc.md`, `docs/cong-thuc.md` và toàn bộ `src/bot_phan_tich/` trước khi sửa bất cứ thứ gì.

## 1. Hướng đi mới

**Chiến lược phân tích: thuần phân tích kỹ thuật, dựa trên ba hệ chỉ báo — MACD, RSI và Ichimoku Kinko Hyo.** Bỏ toàn bộ hướng cũ (HMM, F-Score, M-Score, Z-Score, RS Rating, VCP, Trend Template, triple-barrier, LightGBM, SHAP).

**Năm nhóm chức năng của bot:**

1. **Tra cứu mã cổ phiếu** — thông tin cơ bản doanh nghiệp, các chỉ số tài chính chính, các cập nhật/sự kiện gần nhất.
2. **Khuyến nghị mua/bán** — dựa trên hợp lưu của ba hệ chỉ báo, kèm vùng giá vào, cắt lỗ, mục tiêu.
3. **Lọc cổ phiếu** — screener theo điều kiện kỹ thuật và điều kiện cơ bản.
4. **Bình luận tình hình tài chính doanh nghiệp** — phân tích báo cáo tài chính hợp nhất đã kiểm toán qua các năm bằng kỹ thuật text mining, xuất ra nhận xét bằng tiếng Việt.
5. **Cảnh báo tự động (phần cộng điểm)** — cảnh báo cho các mã trong danh sách theo dõi của người dùng, và khuyến nghị tự động cuối phiên khi cổ phiếu có biến động đáng chú ý.

**Dữ liệu:** DNSE là nguồn chính (realtime), Vietcap là nguồn dự phòng. **Chưa có API key tại thời điểm này** — xem mục 6, tuyệt đối không tự bịa endpoint hay tự viết logic kết nối realtime.

## 2. Giữ lại, xoá đi

**Giữ nguyên, chỉ sửa khi thật cần:**

- `src/bot_phan_tich/config.py`, `logging_conf.py`
- `src/bot_phan_tich/data/` — toàn bộ: `base.py`, `router.py`, `cleaner.py`, `cache.py`, `dnse.py`, `vietcap.py`, `universe.py`
- `src/bot_phan_tich/bot/` — `main.py` (giữ nguyên middleware bắt lỗi), `charts.py`, `keyboards.py`, `formatters.py`, `scheduler.py`
- `src/bot_phan_tich/risk/sizing.py`, `risk/stops.py`, `risk/constraints.py`
- `src/bot_phan_tich/backtest/` — giữ, đề bài vẫn yêu cầu đánh giá hiệu năng 3–6 tháng
- `tests/test_cleaner.py`, `tests/test_indicators.py`, `tests/test_sizing.py`
- `config/`, `scripts/init_db.py`, `scripts/backfill_data.py`, `Dockerfile`, `docker-compose.yml`, `tasks.ps1`, `.env.example`, `.gitignore`

**Xoá hẳn (không giữ lại dưới dạng comment hay thư mục legacy):**

- `src/bot_phan_tich/ml/` — cả thư mục
- `src/bot_phan_tich/strategy/funnel.py`, `vcp.py`, `trend_template.py`, `rs_rating.py`, `squeeze.py`
- `src/bot_phan_tich/features/regime.py`, `fundamentals.py`, `flow.py`, `store.py`
- `scripts/train_model.py`
- `tests/test_labeling.py`
- Mọi import và tham chiếu còn sót lại tới các module trên (kiểm tra kỹ `bot/handlers/`, `config/settings.yaml`)

**Đổi chỗ:** `features/indicators.py` chuyển thành nền của gói `indicators/` mới (mục 3).

## 3. Cấu trúc đích

```
src/bot_phan_tich/
├── config.py
├── logging_conf.py
├── data/                      giữ nguyên
│   ├── base.py  router.py  cleaner.py  cache.py
│   ├── dnse.py  vietcap.py  universe.py
│   └── realtime.py            MỚI — chỉ khai báo giao diện, chưa cài (mục 6)
├── indicators/                MỚI — tách từ features/indicators.py
│   ├── common.py              SMA, EMA, ATR, khối lượng, tiện ích chung
│   ├── macd.py
│   ├── rsi.py
│   ├── ichimoku.py
│   └── divergence.py          phát hiện phân kỳ giá với MACD/RSI
├── analysis/                  MỚI
│   ├── scoring.py             chấm điểm hợp lưu ba hệ -> khuyến nghị
│   ├── lookup.py              tra cứu mã: hồ sơ, chỉ số, cập nhật gần đây
│   ├── screener.py            lọc cổ phiếu
│   └── fintext.py             text mining báo cáo tài chính
├── alerts/                    MỚI
│   ├── watchlist.py           quản lý danh sách theo dõi
│   └── eod.py                 quét cuối phiên, sinh cảnh báo
├── risk/                      giữ
├── backtest/                  giữ, đơn giản hoá theo mục 7
└── bot/
    ├── main.py  charts.py  keyboards.py  formatters.py  scheduler.py
    └── handlers/
        ├── common.py          /start /help /market
        ├── lookup.py          /tracuu
        ├── recommend.py       /khuyennghi /bieudo
        ├── screener.py        /loc
        ├── finreport.py       /bctc
        └── watchlist.py       /theodoi /bosach /danhsach /canhbao
```

## 4. Chi tiết ba hệ chỉ báo

Tự cài bằng `pandas`/`numpy`, **không** gọi thư viện chỉ báo bên ngoài. Lý do: khi bảo vệ đồ án phải chỉ được thẳng vào dòng code ứng với công thức. Mỗi hàm nhận `pd.DataFrame` có cột `time, open, high, low, close, volume` và trả về `pd.Series`/`pd.DataFrame` cùng độ dài, có docstring ghi rõ công thức.

### 4.1. `indicators/macd.py`

```
EMA_n(t) = alpha*P(t) + (1-alpha)*EMA_n(t-1),   alpha = 2/(n+1)
MACD     = EMA_12 - EMA_26
Signal   = EMA_9(MACD)
Hist     = MACD - Signal
```

Hàm cần có:
- `macd(frame, fast=12, slow=26, signal=9) -> DataFrame[macd, signal, hist]`
- `macd_state(frame) -> dict` trả về: `cross` (`"golden"` / `"death"` / `None`), `bars_since_cross`, `hist_slope` (độ dốc histogram 3 phiên gần nhất), `above_zero` (MACD nằm trên hay dưới đường 0).

Quy ước diễn giải: giao cắt **trên** đường 0 mạnh hơn giao cắt dưới đường 0; histogram thu hẹp dù chưa cắt là dấu hiệu động lượng suy yếu.

### 4.2. `indicators/rsi.py`

RSI 14 phiên, làm mượt theo phương pháp Wilder (`ewm(alpha=1/14, adjust=False)`).

**Không dùng ngưỡng cứng 30/70.** Thay bằng ngưỡng thích ứng theo phân vị lịch sử của chính mã đó:

```
upper(t) = phân vị 90 của RSI trong 252 phiên gần nhất, kẹp trong [65, 85]
lower(t) = phân vị 10 của RSI trong 252 phiên gần nhất, kẹp trong [15, 35]
```

Lý do (ghi vào docstring): trong xu hướng tăng mạnh, RSI có thể nằm trên 70 nhiều tuần liền; bán theo ngưỡng cứng là bán mất hàng tốt. Ngưỡng thích ứng khắc phục điều đó và là điểm khác biệt so với cách làm phổ thông.

Hàm cần có:
- `rsi(series, period=14) -> Series`
- `adaptive_bands(series, lookback=252) -> DataFrame[upper, lower]`
- `rsi_state(frame) -> dict`: `value`, `zone` (`"qua_mua"` / `"trung_tinh"` / `"qua_ban"`), `upper`, `lower`, `slope` (độ dốc RSI 5 phiên).

### 4.3. `indicators/ichimoku.py`

Cài đủ **năm** thành phần, không cắt bớt:

```
Tenkan-sen  (Chuyển)   = (max(High,9)  + min(Low,9))  / 2
Kijun-sen   (Cơ sở)    = (max(High,26) + min(Low,26)) / 2
Senkou A    (Dẫn A)    = (Tenkan + Kijun) / 2,  dịch tới trước 26 phiên
Senkou B    (Dẫn B)    = (max(High,52) + min(Low,52)) / 2,  dịch tới trước 26 phiên
Chikou      (Trễ)      = Close,  dịch lùi 26 phiên
Kumo (mây)             = vùng giữa Senkou A và Senkou B
```

Hàm cần có:
- `ichimoku(frame, tenkan=9, kijun=26, senkou_b=52, shift=26) -> DataFrame`
- `ichimoku_state(frame) -> dict` gồm:
  - `price_vs_kumo`: `"tren_may"` / `"trong_may"` / `"duoi_may"`
  - `tk_cross`: giao cắt Tenkan/Kijun, kèm vị trí so với mây (giao cắt tăng **trên** mây là tín hiệu mạnh nhất, trong mây là trung tính, dưới mây là yếu)
  - `kumo_twist`: mây phía trước có đổi màu trong 26 phiên tới không (Senkou A cắt Senkou B)
  - `chikou_free`: đường trễ có nằm thoáng phía trên giá của 26 phiên trước không
  - `kumo_thickness`: độ dày mây chuẩn hoá theo ATR — mây dày là hỗ trợ/kháng cự mạnh

**Về tham số 9-26-52:** đây là bộ số gốc từ thị trường Nhật thập niên 1960 dựa trên tuần làm việc 6 ngày. Thêm hằng số `ICHIMOKU_PRESETS` trong file, gồm bộ gốc `(9, 26, 52)` và bộ hiệu chỉnh cho tuần 5 ngày `(7, 22, 44)`, cho phép chọn qua `config/settings.yaml`. Ghi rõ trong docstring rằng nhóm đã biết nguồn gốc tham số và có phương án hiệu chỉnh — đây là câu giảng viên rất dễ hỏi.

### 4.4. `indicators/divergence.py`

Phát hiện phân kỳ giữa giá và MACD/RSI — đây là phần khó sao chép nhất trong bộ ba, vì cần so sánh chuỗi đỉnh/đáy qua nhiều phiên chứ không phải điều kiện của một phiên.

- `find_swings(series, order=5) -> list[(index, value, "H"|"L")]` — tìm đỉnh/đáy cục bộ bằng cửa sổ trượt.
- `detect_divergence(frame, oscillator, lookback=60) -> dict` trả về `type` (`"bullish"` / `"bearish"` / `None`), `strength`, `swing_points`.

Quy ước: phân kỳ dương = giá tạo đáy thấp hơn nhưng chỉ báo tạo đáy cao hơn. Phân kỳ âm = ngược lại.

## 5. Chấm điểm và khuyến nghị — `analysis/scoring.py`

Ba hệ chỉ báo chấm độc lập, mỗi hệ cho điểm trong khoảng **-100 đến +100**, sau đó gộp có trọng số.

```
Điểm tổng = w_macd*S_macd + w_rsi*S_rsi + w_ichi*S_ichi
mặc định: w_macd = 0.30, w_rsi = 0.25, w_ichi = 0.45
```

Trọng số đặt trong `config/settings.yaml`, không hard-code. Ichimoku nặng nhất vì nó là hệ thống xu hướng hoàn chỉnh, còn MACD và RSI là chỉ báo động lượng đơn lẻ.

**Quy tắc bắt buộc — hợp lưu, không cộng dồn mù quáng:**

- Không phát khuyến nghị MUA khi giá nằm **dưới** mây Kumo, bất kể điểm tổng cao bao nhiêu. Ichimoku có quyền phủ quyết.
- Có phân kỳ âm → trừ thẳng 25 điểm.
- Khối lượng phiên dưới 50% trung bình 20 phiên → hạ độ tin cậy xuống một bậc (tín hiệu không có dòng tiền xác nhận).

**Ánh xạ điểm sang khuyến nghị:**

| Điểm tổng | Khuyến nghị |
|---|---|
| >= +60 | MUA |
| +20 đến +60 | TÍCH LUỸ |
| -20 đến +20 | THEO DÕI |
| -60 đến -20 | GIẢM TỶ TRỌNG |
| <= -60 | BÁN |

Mỗi khuyến nghị phải kèm:
- Vùng giá vào hợp lý
- Cắt lỗ: `max(giá - 1.5*ATR14, Kijun-sen)` — lấy mức gần hơn
- Mục tiêu: `giá + 3*ATR14`, và mức kháng cự Ichimoku gần nhất
- Tỷ lệ lợi nhuận/rủi ro
- **Ba lý do bằng tiếng Việt**, sinh từ trạng thái thực tế của từng hệ chỉ báo, không phải câu mẫu cố định

Trả về dataclass `Recommendation` với đủ các trường trên cộng `component_scores: dict[str, float]` để bot hiển thị điểm từng hệ.

## 6. Realtime — CHỈ dựng khung, CHƯA cài

Nhóm chưa có API key. Yêu cầu:

Tạo `data/realtime.py` gồm:
- `RealtimeQuote` — dataclass: `symbol, price, change, change_pct, volume, timestamp, source`
- `RealtimeProvider` — lớp trừu tượng với `subscribe(symbols)`, `unsubscribe(symbols)`, `latest(symbol)`, `close()`
- `DnseRealtimeProvider(RealtimeProvider)` — **stub**: mỗi phương thức `raise NotImplementedError` kèm docstring ghi rõ: cần API key/secret từ EntradeX, DNSE dùng WebSocket/MQTT cho realtime, đây là chỗ sẽ cài
- `VietcapRealtimeProvider(RealtimeProvider)` — stub tương tự, đánh dấu là nguồn dự phòng
- `NullRealtimeProvider(RealtimeProvider)` — cài đặt thật, luôn trả `None`, dùng khi realtime tắt

Thêm vào `config/settings.yaml`:

```yaml
realtime:
  enabled: false
  provider: dnse
  fallback: vietcap
  reconnect_seconds: 5
```

**Ràng buộc tuyệt đối:** khi `realtime.enabled: false` (mặc định), toàn bộ bot phải chạy bình thường bằng dữ liệu cuối phiên. Không được có bất kỳ đường code nào bắt buộc phải có realtime mới chạy được. Không tự bịa URL WebSocket, không tự đoán tên topic, không viết logic kết nối. Chỉ dựng giao diện và ghi TODO rõ ràng.

## 7. Tra cứu — `analysis/lookup.py`

`lookup(symbol) -> CompanyProfile` gồm ba khối:

1. **Hồ sơ:** tên đầy đủ, sàn niêm yết, ngành, ngày niêm yết, vốn điều lệ, số lượng cổ phiếu lưu hành, mô tả ngắn hoạt động kinh doanh.
2. **Chỉ số chính:** giá hiện tại, thay đổi, khối lượng, vốn hoá, P/E, P/B, EPS, ROE, ROA, biên lợi nhuận ròng, nợ/vốn chủ sở hữu, cổ tức. Mỗi chỉ số kèm so sánh với **trung vị ngành** nếu lấy được.
3. **Cập nhật gần đây:** sự kiện doanh nghiệp (cổ tức, phát hành, đại hội cổ đông), báo cáo tài chính công bố gần nhất, tin tức nếu nguồn có.

Lấy dữ liệu qua `data/router.py`, không gọi thẳng nhà cung cấp. Trường nào không lấy được thì để `None` và hiển thị "không có dữ liệu" — **không được bịa số**.

## 8. Lọc cổ phiếu — `analysis/screener.py`

`screen(criteria: ScreenCriteria) -> list[ScreenResult]`

Điều kiện kỹ thuật: khuyến nghị tối thiểu, điểm tổng tối thiểu, vị trí so với mây Kumo, trạng thái giao cắt MACD, vùng RSI, có phân kỳ dương, khối lượng so với trung bình 20 phiên.

Điều kiện cơ bản: khoảng P/E, khoảng P/B, ROE tối thiểu, vốn hoá tối thiểu, sàn niêm yết, ngành.

Thêm ba bộ lọc dựng sẵn để bot có nút bấm nhanh:
- `"đột phá"` — giá vừa vượt lên trên mây, MACD giao cắt tăng, khối lượng trên 1.5 lần trung bình
- `"tích luỹ"` — giá trong mây, mây mỏng, RSI trung tính, khối lượng cạn
- `"cảnh báo"` — giá thủng xuống dưới mây hoặc có phân kỳ âm

Bắt buộc: quét cả sàn phải chạy trên dữ liệu **từ cache**, có thanh tiến độ ghi log, và giới hạn thời gian. Nếu quá `screener.timeout_seconds` thì trả về kết quả đã có kèm ghi chú, không treo bot.

## 9. Text mining báo cáo tài chính — `analysis/fintext.py`

Đây là phần tạo khác biệt lớn nhất của nhóm. Mục tiêu: đọc báo cáo tài chính **hợp nhất đã kiểm toán** qua các năm và xuất ra bình luận bằng tiếng Việt về tình hình tài chính doanh nghiệp.

**Đầu vào (hai đường, cài cả hai):**
- Dữ liệu có cấu trúc từ `data/router.py` — `financials(symbol, period="year")`
- Tệp PDF báo cáo do người dùng gửi vào bot hoặc đặt trong `data/reports/<MÃ>/`

**Xử lý:**

1. `extract_text(pdf_path) -> str` — dùng `pdfplumber` hoặc `pypdf`, giữ được cấu trúc đoạn.
2. `segment_sections(text) -> dict` — tách các phần theo tiêu đề: ý kiến kiểm toán, bảng cân đối kế toán, kết quả kinh doanh, lưu chuyển tiền tệ, thuyết minh. Dùng regex trên các mẫu tiêu đề tiếng Việt thường gặp.
3. `audit_opinion(text) -> dict` — phân loại ý kiến kiểm toán thành `"chấp nhận toàn phần"` / `"ngoại trừ"` / `"từ chối"` / `"trái ngược"` bằng từ điển cụm từ. **Ý kiến ngoại trừ là tín hiệu cảnh báo rất mạnh** và phải được nêu lên đầu tiên trong bình luận.
4. `risk_keywords(text) -> list[Hit]` — quét từ điển rủi ro, trả về từ khoá kèm câu chứa nó. Từ điển tối thiểu gồm các nhóm:
   - Nợ và thanh khoản: `nợ xấu`, `nợ quá hạn`, `quá hạn thanh toán`, `vi phạm cam kết vay`, `khả năng thanh toán`
   - Dự phòng: `trích lập dự phòng`, `dự phòng giảm giá`, `dự phòng phải thu khó đòi`, `tổn thất tài sản`
   - Hoạt động liên tục: `khả năng hoạt động liên tục`, `nghi ngờ đáng kể`, `lỗ luỹ kế`, `âm vốn chủ sở hữu`
   - Bên liên quan: `giao dịch với bên liên quan`, `cho vay bên liên quan`, `công ty mẹ`
   - Pháp lý: `tranh chấp`, `kiện tụng`, `xử phạt`, `thanh tra`, `truy thu thuế`
   Mỗi nhóm có trọng số rủi ro riêng, đặt trong `config/risk_keywords.yaml` để dễ bổ sung.
5. `trend_analysis(financials) -> dict` — tính tốc độ tăng trưởng kép nhiều năm của doanh thu, lợi nhuận sau thuế, tổng tài sản, vốn chủ sở hữu; theo dõi biến động biên lợi nhuận gộp và biên ròng; tính chất lượng lợi nhuận bằng tỷ lệ dòng tiền hoạt động trên lợi nhuận sau thuế (dưới 0.8 kéo dài là dấu hiệu lợi nhuận không đi kèm tiền thật).
6. `generate_commentary(...) -> str` — **sinh nhận xét bằng quy tắc và mẫu câu, không dùng mô hình ngôn ngữ**. Bố cục cố định:
   - Ý kiến kiểm toán và cảnh báo (nếu có)
   - Tăng trưởng qua các năm
   - Khả năng sinh lời
   - Cơ cấu tài chính và đòn bẩy
   - Chất lượng lợi nhuận và dòng tiền
   - Các rủi ro phát hiện trong thuyết minh
   - Kết luận một đoạn

Mỗi nhận xét phải **dẫn được số cụ thể** và **ghi rõ năm**. Không dùng câu chung chung kiểu "tình hình tài chính khả quan" mà không có số đi kèm.

Về tiếng Việt: dùng regex và từ điển trước; chỉ thêm `underthesea` nếu thật sự cần tách từ. **Không** đưa PhoBERT hay mô hình học sâu vào — quá nặng cho khuôn khổ đồ án và khó giải thích khi bảo vệ.

## 10. Cảnh báo — `alerts/`

`alerts/watchlist.py`: thêm, xoá, liệt kê mã theo dõi cho từng `chat_id`, lưu vào SQLite (bảng `subscriptions` đã có sẵn trong `data/cache.py`).

`alerts/eod.py`: hàm `run_eod_scan()` chạy sau giờ đóng cửa, với mỗi mã trong danh sách theo dõi của mọi người dùng:
- Tính lại khuyến nghị
- So với khuyến nghị lưu lần trước
- **Chỉ gửi tin khi có thay đổi đáng kể**, theo các điều kiện: khuyến nghị đổi bậc, MACD giao cắt mới, giá xuyên qua mây Kumo, RSI vào/ra vùng cực trị, khối lượng đột biến trên 2 lần trung bình 20 phiên, giá biến động quá 4% trong phiên
- Ghi lại trạng thái mới vào bảng `signals` để lần sau so sánh

Chống làm phiền: tối đa 3 cảnh báo mỗi mã mỗi ngày; nếu một người theo dõi nhiều mã thì gộp thành **một tin nhắn duy nhất**, không bắn từng tin.

Nối `run_eod_scan` vào `bot/scheduler.py` theo cron trong `config/settings.yaml` (mặc định 15h05 các ngày làm việc).

## 11. Bộ lệnh bot

Đăng ký **cả tên tiếng Việt và tiếng Anh** cho mỗi lệnh (aliases) để gõ kiểu nào cũng được.

| Lệnh | Bí danh | Chức năng |
|---|---|---|
| `/tracuu <MÃ>` | `/info` | Hồ sơ + chỉ số chính + cập nhật gần đây |
| `/khuyennghi <MÃ>` | `/rec`, `/kn` | Khuyến nghị, điểm ba hệ, vùng giá vào/cắt lỗ/mục tiêu, ba lý do |
| `/bieudo <MÃ>` | `/chart` | Biểu đồ nến kèm mây Ichimoku, MACD, RSI |
| `/loc` | `/screen` | Lọc cổ phiếu, có nút bấm cho ba bộ lọc dựng sẵn |
| `/bctc <MÃ>` | `/fin` | Bình luận tình hình tài chính từ text mining |
| `/theodoi <MÃ>` | `/sub` | Thêm vào danh sách theo dõi |
| `/bosach <MÃ>` | `/unsub` | Bỏ theo dõi |
| `/danhsach` | `/watchlist` | Xem danh sách theo dõi kèm khuyến nghị hiện tại |
| `/canhbao` | `/alerts` | Bật/tắt cảnh báo tự động |
| `/help` | `/start` | Hướng dẫn + menu nút bấm |

Yêu cầu về trình bày, viết trong `bot/formatters.py`:
- Mọi tin nhắn dùng `parse_mode=HTML`, escape nội dung do người dùng nhập
- Thẻ khuyến nghị có bố cục cố định: dòng đầu là mã và khuyến nghị, khối hai là vùng giá, khối ba là điểm ba hệ, khối bốn là ba lý do
- Mọi tin nhắn có tín hiệu đều kèm một dòng miễn trừ trách nhiệm
- Lệnh nào chạy quá 2 giây thì gửi trước "Đang xử lý..." rồi sửa tin nhắn đó khi xong

Cập nhật `bot/charts.py`: vẽ mây Ichimoku (tô vùng giữa Senkou A và B, đổi màu theo A trên hay dưới B), thêm hai khung phụ cho MACD và RSI kèm hai đường ngưỡng thích ứng.

## 12. Ràng buộc kỹ thuật

- Python 3.10+, type hints đầy đủ, docstring tiếng Việt không dấu cho phần mô tả kỹ thuật (tránh lỗi encoding trên Windows), chuỗi hiển thị cho người dùng thì có dấu bình thường.
- **Không module nào ngoài `data/` được gọi mạng.** Mọi truy cập dữ liệu đi qua `data/router.py`.
- **Mọi ngưỡng đặt trong `config/settings.yaml`**, không hard-code trong mã nguồn.
- Giữ nguyên middleware `ErrorGuard` trong `bot/main.py`. Handler mới phải chịu được: mã không tồn tại, mã chưa đủ lịch sử, nguồn dữ liệu lỗi, tham số thiếu.
- `requirements.txt`: bỏ `lightgbm`, `hmmlearn`, `shap`, `optuna`, `scikit-learn`, `scipy` nếu không còn dùng; thêm `pdfplumber`.
- Cập nhật `README.md`, `docs/kien-truc.md`, `docs/cong-thuc.md` cho khớp hướng mới. `docs/cong-thuc.md` phải ghi đầy đủ công thức MACD, RSI thích ứng, năm thành phần Ichimoku, cách chấm điểm hợp lưu.

## 13. Kiểm thử

Viết mới, tối thiểu:
- `tests/test_macd.py` — giao cắt vàng/chết trên chuỗi dựng sẵn; histogram đổi dấu đúng thời điểm
- `tests/test_rsi.py` — RSI nằm trong [0,100]; ngưỡng thích ứng bị kẹp đúng biên; chuỗi tăng đơn điệu cho RSI cao
- `tests/test_ichimoku.py` — Senkou dịch tới trước đúng 26 phiên, Chikou dịch lùi đúng 26 phiên; phân loại trên/trong/dưới mây đúng trên dữ liệu dựng tay
- `tests/test_divergence.py` — phát hiện đúng phân kỳ dương và âm trên chuỗi dựng sẵn
- `tests/test_scoring.py` — quyền phủ quyết của Ichimoku (dưới mây thì không bao giờ ra MUA); ánh xạ điểm sang khuyến nghị đúng ở các mốc biên
- `tests/test_fintext.py` — phân loại đúng bốn loại ý kiến kiểm toán; bắt đúng từ khoá rủi ro trong đoạn văn mẫu

Giữ `tests/test_cleaner.py` và `tests/test_sizing.py`. Sửa `tests/test_indicators.py` cho khớp cấu trúc `indicators/` mới. `pytest -q` phải xanh toàn bộ khi xong.

## 14. Thứ tự thực hiện

Làm tuần tự, sau mỗi bước chạy `pytest -q` và báo lại:

1. Xoá các module thuộc hướng cũ, dọn sạch import gãy. Chạy `pytest -q`, chấp nhận việc test cũ đỏ ở bước này.
2. Dựng gói `indicators/` (common, macd, rsi, ichimoku, divergence) + test cho từng file.
3. Dựng `analysis/scoring.py` + test.
4. Dựng `data/realtime.py` (chỉ giao diện + stub) và cập nhật `config/settings.yaml`.
5. Dựng `analysis/lookup.py` và `analysis/screener.py`.
6. Dựng `analysis/fintext.py` + `config/risk_keywords.yaml` + test.
7. Dựng `alerts/watchlist.py` và `alerts/eod.py`, nối vào scheduler.
8. Viết lại handlers và formatters, cập nhật `charts.py`.
9. Đơn giản hoá `backtest/` cho khớp tín hiệu mới: backtest chạy trên khuyến nghị của `scoring.py`, giữ nguyên phần trừ phí, thuế và ràng buộc T+2.
10. Cập nhật `README.md` và `docs/`, dọn `requirements.txt`, chạy `ruff check src tests` và `pytest -q` lần cuối.

## 15. Nguyên tắc chung

- Không bịa dữ liệu, không bịa endpoint. Thiếu gì thì để `None` và ghi TODO rõ ràng.
- Không cài gì liên quan tới realtime cho tới khi có API key.
- Ưu tiên code đọc được hơn code ngắn. Hàm dài quá 50 dòng thì tách.
- Mỗi module có docstring đầu file giải thích **nó giải quyết vấn đề gì**, không chỉ nó làm gì.
- Sau mỗi bước trong mục 14, dừng lại báo cáo ngắn gọn những gì đã đổi trước khi làm tiếp.
