"""Tạo bộ ảnh mẫu (kèm đáp án .txt) để đo độ chính xác.  Chạy: python scripts/make_samples.py

Cần font có đủ chữ Việt và chữ Hán. Có thể đặt OCR_FONT_LATIN / OCR_FONT_CJK để chỉ font."""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "samples"

LATIN_FONTS = [os.environ.get("OCR_FONT_LATIN", ""),
               r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
               "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
CJK_FONTS = [os.environ.get("OCR_FONT_CJK", ""),
             r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simsun.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]


def pick(paths: list[str]) -> str:
    for p in paths:
        if p and Path(p).exists():
            return p
    sys.exit("Không tìm thấy font phù hợp, hãy đặt OCR_FONT_LATIN / OCR_FONT_CJK.")


LATIN, CJK = pick(LATIN_FONTS), pick(CJK_FONTS)

MIXED = [
    ("Tiếng Việt: Hôm nay trời đẹp, chúng tôi đi dạo quanh Hồ Gươm.", "l"),
    ("Nguyễn Thị Thu Hương - Đường Trường Chinh, Quận Đống Đa, Hà Nội", "l"),
    ("The quick brown fox jumps over the lazy dog 0123456789", "l"),
    ("中文测试：今天天气很好，我们一起去公园散步。", "c"),
    ("繁體中文：歡迎使用文字辨識工具，準確率很高。", "c"),
    ("Trộn lẫn: Xin chào 你好 world, giá 1.250.000đ (含税)", "c"),
]
PARA = [
    ("Ăn quả nhớ kẻ trồng cây, ơn người cho đất, ơn người hạt gieo.", "l"),
    ("Tiếng Việt có sáu thanh: ngang, huyền, sắc, hỏi, ngã, nặng.", "l"),
    ("Cộng hòa Xã hội Chủ nghĩa Việt Nam - Độc lập - Tự do - Hạnh phúc", "l"),
    ("Hóa đơn số 0045821 ngày 12/10/2026, tổng cộng: 2.345.600 VNĐ.", "l"),
    ("Người học chữ Hán thường bắt đầu từ 汉字, 学习, 你好 và 谢谢.", "c"),
    ("Email: nguyen.van.a@example.com | Điện thoại: 0912 345 678", "l"),
]


def render(lines, size, fg="black", bg="white", pad=24, gap=1.9):
    fl, fc = ImageFont.truetype(LATIN, size), ImageFont.truetype(CJK, size)
    h = int(pad * 2 + len(lines) * size * gap)
    w = int(max(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(t, font=fc if k == "c" else fl)
                for t, k in lines) + pad * 2)
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    for i, (t, k) in enumerate(lines):
        d.text((pad, pad + i * size * gap), t, fill=fg, font=fc if k == "c" else fl)
    return img


def save(name, img, lines, jpeg=None):
    OUT.mkdir(exist_ok=True)
    if jpeg:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=jpeg)
        img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    img.save(OUT / f"{name}.png")
    (OUT / f"{name}.txt").write_text("\n".join(t for t, _ in lines), encoding="utf-8")
    print("tạo", name, img.size)


if __name__ == "__main__":
    save("sample_mixed", render(MIXED, 34), MIXED)
    save("sample_small", render(MIXED, 15, gap=2.2), MIXED)
    save("sample_dark", render(MIXED, 28, fg=(230, 230, 230), bg=(30, 32, 38)), MIXED)
    save("sample_paragraph", render(PARA, 26), PARA)
    noisy = render(PARA, 22).filter(ImageFilter.GaussianBlur(0.8))
    save("sample_noisy", noisy, PARA, jpeg=35)
