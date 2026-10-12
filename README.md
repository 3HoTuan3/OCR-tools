# ocr-tool — chụp vùng màn hình, Ctrl+V ra chữ, dịch luôn (Việt · Anh · Trung)

Một biểu tượng nhỏ nổi trên màn hình (Windows/Linux). **Bấm trái → kéo chọn vùng có chữ → dán (Ctrl+V)**, hoặc chuyển sang tab
**Dịch** để dịch sang ngôn ngữ bạn muốn. **Bấm phải** để mở menu cài đặt. OCR chạy offline hoàn toàn trên CPU;
chỉ riêng việc dịch (mặc định) cần Internet.

## Dùng nhanh

1. Chạy `ocr-tray.bat`. Một ô vuông nhỏ (khung ngắm + vài dòng chữ) nổi ở góc dưới phải màn hình, luôn ở trên cùng.
   **Kéo** nó tới chỗ bạn muốn, vị trí được nhớ cho lần sau. Biểu tượng khay hệ thống (trong mũi tên **^**) vẫn còn để bật/tắt cửa sổ nổi.
2. **Bấm trái** vào ô vuông → màn hình mờ đi → **kéo chuột** chọn vùng có chữ (hiện kích thước; `Esc` hoặc chuột phải để huỷ), thả chuột.
3. Vài giây sau chữ **đã nằm trong clipboard** (Ctrl+V để dán, Win+V để xem lịch sử clipboard) và hiện **cửa sổ kết quả**:
   - tab **Bắt chữ**: chữ gốc, sửa được trước khi chép; nút **Chép**.
   - tab **Dịch**: chọn ngôn ngữ đích (nút `→ Tiếng Việt ▾`); bản dịch tự được chép vào clipboard.
     Clipboard luôn là chữ của tab bạn đang xem, nên quay lại tab Bắt chữ là có lại chữ gốc.
   Cùng ngôn ngữ với đích thì tự đảo chiều (chữ Việt + đích Việt → dịch sang English).
4. **Bấm phải** vào ô vuông → menu: sau khi chụp làm gì (hiện cửa sổ / dịch ngay / chỉ chép), ngôn ngữ và công cụ dịch,
   kiểu chữ xuất ra (xuống dòng / một đoạn / bảng cho Excel), lịch sử (bấm một mục để chép lại), cỡ + độ trong suốt của ô nổi,
   phím tắt toàn cục, khởi động cùng máy, ẩn ô nổi, thoát.

App **không** can thiệp Win+Shift+S và **không** theo dõi clipboard. Nó chỉ ghi vào clipboard khi bạn tự chụp và OCR ra được chữ;
nếu không thấy chữ nào thì clipboard giữ nguyên. Ô nổi tự ẩn trong lúc chụp nên không lọt vào ảnh.

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

## Gỡ cài đặt

```bat
uninstall.bat        rem Windows (hỏi từng bước; thêm /y để gỡ nhanh, không hỏi)
```
```bash
bash uninstall.sh    # Linux (thêm -y để gỡ nhanh)
```
Script sẽ: tắt app khay đang chạy → bỏ mục "khởi động cùng máy" → xoá `.venv`, `tessdata` và file build trong thư mục dự án →
xoá dữ liệu người dùng (cấu hình, lịch sử, log; có hỏi) → trên Windows hỏi có gỡ luôn Tesseract (cài bằng winget) không →
hỏi có xoá cả thư mục dự án không. Chế độ nhanh (`/y`, `-y`) giữ lại Tesseract và thư mục dự án.
Gói hệ thống trên Linux (`tesseract-ocr`, `python3-tk`…) không bị đụng tới.

## Menu chuột phải

| Mục | Ý nghĩa |
|---|---|
| Chụp vùng để OCR | Giống bấm trái |
| Sau khi chụp | *Hiện cửa sổ kết quả* (mặc định) · *Dịch ngay* (mở thẳng tab Dịch) · *Chỉ chép chữ* (như bản đầu, chỉ báo nhỏ) |
| Dịch sang: … | Ngôn ngữ đích: Việt, English, 中文 (简/繁), 日本語, 한국어, Français, Deutsch, Español, Português, Русский, Italiano, ไทย, Bahasa Indonesia |
| Công cụ dịch | *Google* (mặc định, cần Internet) hoặc *Argos* (offline, tuỳ chọn); *Tự chép chữ của tab đang xem* |
| Kiểu chữ xuất ra | Giữ xuống dòng · Gộp một đoạn · **Bảng** (các ô cách bằng Tab, dán thẳng vào Excel/Sheets) |
| Lịch sử (n) | 8 lần chụp gần nhất, bấm để chép lại; bật/tắt lưu lịch sử (20 lần gần nhất, ảnh + chữ); mở thư mục lịch sử |
| Cài đặt cửa sổ nổi | Kích thước, độ trong suốt khi nghỉ, luôn ở trên cùng, đưa về góc màn hình |
| Thông báo khi chép xong | Chỉ áp dụng khi chọn "Chỉ chép chữ" |
| Phím tắt toàn cục | Ctrl+Alt+O để chụp ở bất kỳ đâu (chỉ Windows, mặc định tắt; đổi phím bằng `hotkey` trong config) |
| Khởi động cùng máy | Ghi vào registry `HKCU\...\Run` |
| Mở file log · Ẩn cửa sổ nổi · Thoát | Ẩn cần biểu tượng khay để mở lại (hoặc chạy lại `ocr-tray.bat`) |

Biểu tượng khay: bấm trái = chụp; bấm phải = chụp / hiện cửa sổ nổi / khởi động cùng máy / log / thoát.

Cấu hình nâng cao: `%LOCALAPPDATA%\ocrtool\config.json` (vd. `delay_ms` = thời gian chờ để cửa sổ nổi ẩn hẳn trước khi chụp,
`hotkey` = `"ctrl+shift+f9"`, `float_opacity` = `0.5`).

### Dịch
- **Google (mặc định):** dùng điểm cuối dịch công khai của Google, không cần khoá. Chữ **chỉ được gửi đi khi bạn mở tab Dịch**.
  Đây là cổng không chính thức nên có thể bị giới hạn tần suất hoặc đổi; app báo lỗi bằng tiếng Việt và chữ gốc không bị mất.
- **Argos (offline, tuỳ chọn):** `.venv\Scripts\pip install argostranslate`, rồi chọn *Công cụ dịch → Argos*. Mô hình ~100 MB mỗi cặp ngôn ngữ
  được tải một lần ở lần dùng đầu; dịch qua tiếng Anh nếu không có cặp trực tiếp. Chất lượng thường thấp hơn Google.

### Lấy ý tưởng từ PowerToys Text Extractor (Win+Shift+T)
Mình đã đọc tài liệu và mô tả mã nguồn của nó. Điều giữ lại: kéo chọn vùng trên lớp phủ rồi tự chép chữ, `Esc` để huỷ,
tách chế độ **bảng** (giữ cột/hàng) với chế độ văn bản thường, xử lý riêng chữ Hán/Nhật (không chèn khoảng trắng giữa các ký tự),
phóng to ảnh nhỏ trước khi nhận dạng. Điều khác: PowerToys dùng engine `Windows.Media.Ocr` có sẵn của Windows (chỉ nhận các
ngôn ngữ đã cài gói OCR), còn ở đây lõi OCR là bản lai PaddleOCR + Tesseract chạy offline, đọc chuẩn cả tiếng Việt có dấu.

**Tài nguyên.** Mỗi lần chụp chạy trong **một tiến trình riêng** (`ocrtool.job`): chụp màn hình → hiện lớp phủ → nạp engine OCR
song song trong lúc bạn đang kéo chuột → OCR → chép chữ → thoát. App nền lúc rảnh chỉ là cửa sổ nổi + khay nhỏ; RAM chỉ tăng
(~230 MB, đo trên Linux) trong vài giây khi đang chụp rồi được trả lại.

**Không muốn chạy app nền?** `ocr-screen.bat` làm đúng một lần chụp rồi thoát (không có biểu tượng). Tạo shortcut tới nó
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
src/ocrtool/   tray.py (app nền: ô nổi + khay) · job.py (một lần chụp, tiến trình riêng) · snip.py (lớp phủ chọn vùng)
               engine.py (lõi lai) · tess.py (gọi Tesseract) · textutil.py (so khớp/chọn kết quả)
               clipboard.py · config.py · autostart.py · capture.py (Wayland, toast) · doctor.py (kiểm tra cài đặt)
               widget.py (ô nổi) · menu.py + appmenu.py (menu chuột phải) · result.py (cửa sổ kết quả)
               translate.py (dịch) · layout.py (chế độ bảng) · hotkey.py · icons.py · uiutil.py
setup / uninstall: setup.bat · setup.sh · uninstall.bat · uninstall.sh
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
- Mới kiểm thử trên Linux (88 test tự động): logic chụp/OCR/dịch/bảng, và toàn bộ giao diện (ô nổi, menu, cửa sổ kết quả, lớp phủ chọn vùng)
  bằng tkinter **thật** trên màn hình ảo. **Chưa chạy thử trên Windows thật**: bấm ra ngoài để đóng menu, ô nổi trong suốt ở góc bo,
  kéo ô nổi giữa nhiều màn hình khác tỉ lệ, phím tắt toàn cục, tự khởi động, `setup.bat` / `uninstall.bat`. Nếu menu không đóng khi bấm ra ngoài,
  nhấn `Esc` hoặc bấm lại vào ô nổi, rồi báo mình.
- Dịch bằng Google cần Internet và là cổng không chính thức; Argos chưa được thử trong môi trường này.
- Chế độ bảng là heuristic theo toạ độ dòng: bảng có đường kẻ, ô gộp hoặc cột canh phải có thể lệch cột.

## Gỡ lỗi

- `python -m ocrtool` báo thiếu `vie` → `python scripts/get_tessdata.py`.
- Không thấy Tesseract → cài rồi mở lại terminal, hoặc đặt biến môi trường `OCR_TESSERACT` trỏ tới `tesseract.exe`.
- Muốn đổi thư mục dữ liệu ngôn ngữ → biến môi trường `OCR_TESSDATA`.
- Lần chạy đầu tiên không cần tải model OCR (đã nằm trong gói `rapidocr`); chỉ `setup` mới tải dữ liệu tiếng Việt cho Tesseract.
