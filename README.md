# ocr-tool — OCR offline cho tiếng Việt, Anh, Trung (Windows & Linux)

Nhẹ, chạy hoàn toàn trên CPU, không cần internet sau khi cài. Dùng được như công cụ dòng lệnh,
chụp vùng màn hình rồi chép chữ vào clipboard, hoặc import làm thư viện Python.

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

## Cài đặt

### Windows
```bat
setup.bat
```
Script sẽ: tạo `.venv`, cài thư viện, cài Tesseract bằng `winget` (nếu chưa có), tải dữ liệu `vie`/`eng`.
Cần Python 3.9+ (khuyên 3.11–3.13) có trong PATH.

### Linux
```bash
sudo apt install tesseract-ocr python3-venv python3-tk xclip   # Debian/Ubuntu
./setup.sh
```
Wayland: chọn vùng màn hình cần `grim`+`slurp`, `gnome-screenshot` hoặc `spectacle`; clipboard cần `wl-clipboard`.

Kiểm tra: `ocr.bat --doctor` (Windows) hoặc `./ocr.sh --doctor` (Linux).

## Sử dụng

```bash
ocr.bat anh.png                  # in chữ nhận được ra màn hình
ocr.bat a.png b.png -o out.txt   # nhiều ảnh, ghi ra file UTF-8
ocr.bat --screen --copy          # kéo chọn vùng màn hình -> chép chữ vào clipboard
ocr.bat --clipboard              # OCR ảnh trong clipboard (sau Win+Shift+S)
ocr.bat anh.png --json           # kèm toạ độ, độ tin cậy, nguồn engine từng dòng
ocr.bat anh.png --min-score 0.8  # bỏ dòng tin cậy thấp
```
(Linux: thay `ocr.bat` bằng `./ocr.sh`.)

**Phím tắt toàn hệ thống trên Windows:** chuột phải `ocr-screen.bat` → *Create shortcut* → *Properties* →
ô *Shortcut key* nhấn `Ctrl+Alt+O`. Bấm phím đó ở bất kỳ đâu → kéo chọn vùng → chữ vào clipboard,
có thông báo nhỏ góc màn hình.

### Dùng như thư viện

```python
from ocrtool import OCREngine

engine = OCREngine()                  # tạo một lần, dùng lại cho nhiều ảnh
result = engine.recognize("anh.png")  # cũng nhận PIL.Image hoặc numpy BGR
print(result.text)
for line in result.lines:
    print(line.text, line.score, line.source, line.box)   # source: paddle | tesseract | mixed
```
Muốn dùng từ dự án khác: `pip install -e D:\Document(D)\CodeTools\ocr-tool` (hoặc đường dẫn tương ứng).

## App chạy ngầm trên khay hệ thống: bấm biểu tượng, kéo chọn, Ctrl+V

```bat
ocr-tray.bat
```
Biểu tượng (khung màu xanh có vài dòng chữ) xuất hiện ở khay hệ thống, thường nằm trong mũi tên **^** cạnh đồng hồ
(kéo ra ngoài nếu muốn ghim). Cách dùng:

1. **Bấm chuột trái** vào biểu tượng → màn hình mờ đi.
2. **Kéo chuột** chọn vùng có chữ (hiện kích thước vùng; `Esc` hoặc chuột phải để huỷ).
3. Thả chuột → vài giây sau chữ nằm trong clipboard, có thông báo "Đã chép N ký tự".
4. **Ctrl+V** để dán, hoặc **Win+V** để xem lịch sử clipboard
   (cần bật: *Settings → System → Clipboard → Clipboard history*).

App **không** can thiệp Win+Shift+S và **không** theo dõi clipboard. Nó chỉ ghi vào clipboard khi bạn tự chụp bằng biểu tượng
này và OCR ra được chữ; nếu không thấy chữ nào thì clipboard giữ nguyên.

Mỗi lần chụp chạy trong **một tiến trình riêng** (`ocrtool.job`): chụp màn hình → hiện lớp phủ → nạp engine OCR song song trong lúc
bạn đang kéo chuột → OCR → chép chữ → thoát. Khay lúc rảnh chỉ là một app nhỏ; RAM chỉ tăng (~230 MB, đo trên Linux)
trong vài giây khi đang chụp rồi được trả lại.

Menu chuột phải vào biểu tượng:

| Mục | Ý nghĩa |
|---|---|
| Chụp vùng để OCR | Giống bấm trái |
| Hiện thông báo khi xong | |
| Gộp các dòng thành một đoạn | Thay vì giữ xuống dòng như trong ảnh |
| Lưu lịch sử ảnh + chữ | Giữ 20 lần chụp gần nhất (ảnh vùng chọn + chữ) trong `%LOCALAPPDATA%\ocrtool\history` |
| Mở thư mục lịch sử | |
| Khởi động cùng máy | Ghi vào registry `HKCU\...\Run` |
| Mở file log / Thoát | |

Cấu hình nâng cao nằm ở `%LOCALAPPDATA%\ocrtool\config.json` (vd. `delay_ms`: thời gian chờ để menu khay đóng trước khi chụp).

**Không muốn chạy khay?** `ocr-screen.bat` làm đúng một lần chụp rồi thoát (không có biểu tượng). Tạo shortcut tới nó
và gán *Shortcut key* (vd. `Ctrl+Alt+O`) là có phím tắt toàn hệ thống.

Nếu biểu tượng không xuất hiện hoặc bấm không thấy gì: chạy `ocr-tray-debug.bat` để thấy lỗi, hoặc mở file log từ menu khay
(`ocrtool.log`). Thiếu tkinter (Python cài thiếu Tcl/Tk) sẽ báo trong thông báo và log.

## Cấu trúc

```
src/ocrtool/   engine.py (lõi lai) · tess.py (gọi Tesseract) · textutil.py (so khớp/chọn kết quả)
               capture.py (chọn vùng, clipboard) · cli.py
               tray.py (app khay) · job.py (một lần chụp, tiến trình riêng) · snip.py (lớp phủ chọn vùng)
               clipboard.py · config.py · autostart.py
scripts/       get_tessdata.py · evaluate.py · make_samples.py
tests/         python -m unittest discover -s tests -v
samples/       ảnh mẫu + đáp án .txt
```

## Hạn chế đã biết

- Dấu gạch ngang dài `–` thường được đọc thành `-`; `，` (toàn góc) và `,` có thể bị lẫn.
- Chữ rất nhỏ (<15px), mờ, hoặc chữ viết tay: độ chính xác giảm. Chữ Đ in hoa đôi khi bị đọc thành B.
- Chữ Hán không được đọc lại bằng Tesseract — hoàn toàn dựa vào Paddle (rất tốt với chữ in, kém với thư pháp/viết tay).
- Văn bản dọc, bảng biểu phức tạp, bố cục nhiều cột: chưa xử lý riêng.
- Muốn nhẹ hơn nữa: `python scripts/get_tessdata.py --fast` (xoá `tessdata/*.traineddata` trước) —
  nhanh và nhỏ hơn nhưng sai số cao hơn một chút.
- Mới kiểm thử trên Linux: toàn bộ logic (tiến trình chụp, khởi động/theo dõi tiến trình con, xử lý lỗi, lịch sử) bằng test tự động,
  khay hệ thống khởi động được trên màn hình ảo. Lớp phủ chọn vùng chỉ thử với tkinter **giả** (không có tkinter thật ở môi trường thử).
  Lớp phủ thật, thông báo của Windows, tự khởi động và `setup.bat` **chưa chạy thử trên Windows thật**.
- Mỗi lần OCR thành công, chữ thay thế nội dung clipboard hiện có (bản cũ vẫn xem được trong Win+V nếu đã bật lịch sử clipboard).

## Gỡ lỗi

- `--doctor` báo thiếu `vie` → `python scripts/get_tessdata.py`.
- Không thấy Tesseract → cài rồi mở lại terminal, hoặc đặt biến môi trường `OCR_TESSERACT` trỏ tới `tesseract.exe`.
- Muốn đổi thư mục dữ liệu ngôn ngữ → biến `OCR_TESSDATA` hoặc `--tessdata`.
- Lần chạy đầu tiên không cần tải model (đã nằm trong gói `rapidocr`).
