# ocr-tool — chụp vùng màn hình, Ctrl+V ra chữ (Việt · Anh · Trung)

App nhỏ chạy ở khay hệ thống Windows/Linux. **Bấm biểu tượng → kéo chọn vùng có chữ → dán (Ctrl+V).**
OCR chạy offline hoàn toàn trên CPU, không cần internet sau khi cài.

## Dùng nhanh

1. Chạy `ocr-tray.bat`. Biểu tượng (khung xanh có vài dòng chữ) hiện ở khay hệ thống, thường nằm trong mũi tên **^**
   cạnh đồng hồ (kéo ra ngoài nếu muốn ghim).
2. **Bấm chuột trái** vào biểu tượng → màn hình mờ đi.
3. **Kéo chuột** chọn vùng có chữ (hiện kích thước vùng; `Esc` hoặc chuột phải để huỷ), rồi thả chuột.
4. Vài giây sau chữ đã nằm trong clipboard và có thông báo "Đã chép N ký tự".
   **Ctrl+V** để dán, hoặc **Win+V** để xem lịch sử clipboard
   (cần bật: *Settings → System → Clipboard → Clipboard history*).

App **không** can thiệp Win+Shift+S và **không** theo dõi clipboard. Nó chỉ ghi vào clipboard khi bạn tự chụp bằng biểu tượng
này và OCR ra được chữ; nếu không thấy chữ nào thì clipboard giữ nguyên.

## Cài đặt

### Windows
```bat
setup.bat
```
Script sẽ: tạo `.venv`, cài thư viện, cài Tesseract bằng `winget` (nếu chưa có), tải dữ liệu tiếng Việt `vie`/`eng`.
Cần Python 3.9+ (khuyên 3.11–3.13) có trong PATH, cài kèm Tcl/Tk (mặc định của bộ cài python.org).
Xong thì chạy `ocr-tray.bat`.

### Linux
```bash
sudo apt install tesseract-ocr python3-venv python3-tk xclip   # Debian/Ubuntu
bash setup.sh
.venv/bin/python -m ocrtool.tray
```
Wayland: chọn vùng màn hình cần `grim`+`slurp`, `gnome-screenshot` hoặc `spectacle`; clipboard cần `wl-clipboard`.
Khay hệ thống trên GNOME cần extension AppIndicator.

Kiểm tra cài đặt: `.venv\Scripts\python.exe -m ocrtool` (Windows) hoặc `.venv/bin/python -m ocrtool` (Linux).
`setup` cũng tự chạy lệnh này ở cuối.

## Tuỳ chỉnh app khay

Bấm chuột phải vào biểu tượng:

| Mục | Ý nghĩa |
|---|---|
| Chụp vùng để OCR | Giống bấm trái |
| Hiện thông báo khi xong | |
| Gộp các dòng thành một đoạn | Thay vì giữ xuống dòng như trong ảnh |
| Lưu lịch sử ảnh + chữ | Giữ 20 lần chụp gần nhất (ảnh vùng chọn + chữ) trong `%LOCALAPPDATA%\ocrtool\history` |
| Mở thư mục lịch sử | |
| Khởi động cùng máy | Ghi vào registry `HKCU\...\Run` |
| Mở file log / Thoát | |

Cấu hình nâng cao: `%LOCALAPPDATA%\ocrtool\config.json` (vd. `delay_ms` = thời gian chờ để menu khay đóng trước khi chụp).

**Tài nguyên.** Mỗi lần chụp chạy trong **một tiến trình riêng** (`ocrtool.job`): chụp màn hình → hiện lớp phủ → nạp engine OCR
song song trong lúc bạn đang kéo chuột → OCR → chép chữ → thoát. Khay lúc rảnh chỉ là một app nhỏ; RAM chỉ tăng
(~230 MB, đo trên Linux) trong vài giây khi đang chụp rồi được trả lại.

**Không muốn chạy khay?** `ocr-screen.bat` làm đúng một lần chụp rồi thoát (không có biểu tượng). Tạo shortcut tới nó
(chuột phải → *Create shortcut*), vào *Properties* và gán *Shortcut key* (vd. `Ctrl+Alt+O`) là có phím tắt toàn hệ thống.

Nếu biểu tượng không xuất hiện hoặc bấm không thấy gì: chạy `ocr-tray-debug.bat` để thấy lỗi, hoặc mở file log từ menu khay
(`ocrtool.log`). Thiếu tkinter (Python cài thiếu Tcl/Tk) sẽ báo trong thông báo và log.

## Dùng như thư viện Python (tuỳ chọn)

App không còn giao diện dòng lệnh. Lõi OCR vẫn là một thư viện nhỏ nếu bạn muốn gọi từ script/dự án khác:

```python
from ocrtool import OCREngine

engine = OCREngine()                  # tạo một lần, dùng lại cho nhiều ảnh
result = engine.recognize("anh.png")  # cũng nhận PIL.Image hoặc numpy BGR
print(result.text)
for line in result.lines:
    print(line.text, line.score, line.source, line.box)   # source: paddle | tesseract | mixed
```
Muốn dùng từ dự án khác: `pip install -e D:\Document(D)\CodeTools\ocr-tool` (hoặc đường dẫn tương ứng).

## Cách hoạt động (và vì sao lai hai engine)

| Việc | Engine | Lý do |
|---|---|---|
| Dò vùng chữ, đọc **Trung + Anh** | PaddleOCR **PP-OCRv6** (qua RapidOCR, ONNX, ~31 MB, có sẵn trong gói pip) | Đọc tiếng Trung rất chuẩn, dò dòng tốt |
| Đọc **tiếng Việt** (và Latin) | **Tesseract** + dữ liệu `vie` | Từ điển của model Paddle **không có** các chữ Việt dấu chồng (ạ ế ệ ỉ ụ…), nên nó làm rơi chữ: "Tiếng Việt" → "Ting Vit" |

Dòng trộn Việt–Trung (`Xin chào 你好 world`) được tách theo tọa độ từng token: đoạn Hán giữ kết quả
Paddle, đoạn Latin đọc lại bằng Tesseract, rồi ghép lại đúng thứ tự.

## Kết quả đo

5 ảnh tổng hợp (`samples/`): dòng trộn, chữ nhỏ 15px, nền tối, đoạn văn nhiều dấu/số/email, ảnh JPEG nén mạnh + mờ.
CER = tỉ lệ ký tự sai (bỏ qua khoảng trắng và kiểu gạch ngang). Chạy lại bằng `python scripts/evaluate.py`.

| | PaddleOCR đơn lẻ | **Bản lai (mặc định)** |
|---|---|---|
| CER tổng | 11.9% | **0.4%** |
| Ảnh chính xác 100% | 0/5 | 3/5 |
| Thời gian | — | ~2.5 s/ảnh trên CPU (khởi tạo engine ~0.5 s, một lần) |
| RAM đỉnh | — | ~460 MB (một engine, ảnh cỡ 1000×400) |

Đây là ảnh tổng hợp do chính dự án tạo, **không phải ảnh thực tế của bạn**. Hãy thử trên ảnh thật rồi đánh giá lại.

## Cấu trúc

```
src/ocrtool/   tray.py (app khay) · job.py (một lần chụp, tiến trình riêng) · snip.py (lớp phủ chọn vùng)
               engine.py (lõi lai) · tess.py (gọi Tesseract) · textutil.py (so khớp/chọn kết quả)
               clipboard.py · config.py · autostart.py · capture.py (Wayland, toast) · doctor.py (kiểm tra cài đặt)
scripts/       get_tessdata.py · evaluate.py · make_samples.py
tests/         python -m unittest discover -s tests -v
samples/       ảnh mẫu + đáp án .txt
```

## Hạn chế đã biết

- Dấu gạch ngang dài `–` thường được đọc thành `-`; `，` (toàn góc) và `,` có thể bị lẫn.
- Chữ rất nhỏ (<15px), mờ, hoặc chữ viết tay: độ chính xác giảm. Chữ Đ in hoa đôi khi bị đọc thành B.
- Chữ Hán không được đọc lại bằng Tesseract — hoàn toàn dựa vào Paddle (rất tốt với chữ in, kém với thư pháp/viết tay).
- Văn bản dọc, bảng biểu phức tạp, bố cục nhiều cột: chưa xử lý riêng.
- Mỗi lần OCR thành công, chữ thay thế nội dung clipboard hiện có (bản cũ vẫn xem được trong Win+V nếu đã bật lịch sử clipboard).
- Muốn nhẹ hơn nữa: `python scripts/get_tessdata.py --fast` (xoá `tessdata/*.traineddata` trước) —
  nhanh và nhỏ hơn nhưng sai số cao hơn một chút.
- Mới kiểm thử trên Linux: toàn bộ logic (tiến trình chụp, khởi động/theo dõi tiến trình con, xử lý lỗi, lịch sử) bằng test tự động,
  khay hệ thống khởi động được trên màn hình ảo. Lớp phủ chọn vùng chỉ thử với tkinter **giả** (không có tkinter thật ở môi trường thử).
  Lớp phủ thật, thông báo của Windows, tự khởi động và `setup.bat` **chưa chạy thử trên Windows thật**.

## Gỡ lỗi

- `python -m ocrtool` báo thiếu `vie` → `python scripts/get_tessdata.py`.
- Không thấy Tesseract → cài rồi mở lại terminal, hoặc đặt biến môi trường `OCR_TESSERACT` trỏ tới `tesseract.exe`.
- Muốn đổi thư mục dữ liệu ngôn ngữ → biến môi trường `OCR_TESSDATA`.
- Lần chạy đầu tiên không cần tải model OCR (đã nằm trong gói `rapidocr`); chỉ `setup` mới tải dữ liệu tiếng Việt cho Tesseract.
