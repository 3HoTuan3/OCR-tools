"""Vẽ biểu tượng bằng Pillow: biểu tượng khay và ô vuông bo góc của cửa sổ nổi."""
from __future__ import annotations

TILE = {"idle": (43, 45, 49), "hover": (62, 65, 72), "busy": (37, 99, 235)}
ACCENT = (96, 165, 250)


def make_icon_image(size: int = 64):
    """Biểu tượng khay 64x64: khung chụp màn hình có góc + vài dòng chữ."""
    from PIL import Image, ImageDraw

    c = (37, 99, 235, 255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=12, fill=(255, 255, 255, 255),
                        outline=c, width=4)
    for i, w in enumerate((38, 30, 36)):
        y = 17 + i * 12
        d.rounded_rectangle((13, y, 13 + w, y + 6), radius=3, fill=c)
    return img


def make_tile(size: int, state: str = "idle"):
    """Ô vuông bo góc màu tối (idle/hover/busy) với khung ngắm + vài dòng chữ; vẽ 4x rồi thu nhỏ cho mịn."""
    from PIL import Image, ImageDraw

    k = 4
    s = size * k
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = TILE.get(state, TILE["idle"]) + (255,)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.24), fill=bg)
    white = (245, 247, 250, 255)
    m, ln, w = int(s * 0.22), int(s * 0.17), max(k * 2, int(s * 0.055))
    for sx in (0, 1):                                  # bốn góc khung ngắm
        for sy in (0, 1):
            x = m if sx == 0 else s - m
            y = m if sy == 0 else s - m
            dx = ln if sx == 0 else -ln
            dy = ln if sy == 0 else -ln
            d.line((x, y, x + dx, y), fill=white, width=w)
            d.line((x, y, x, y + dy), fill=white, width=w)
    accent = (255, 255, 255, 255) if state == "busy" else ACCENT + (255,)
    for i, frac in enumerate((0.34, 0.26, 0.30)):      # ba dòng chữ
        y = int(s * (0.40 + i * 0.105))
        x0 = int(s * 0.33)
        d.rounded_rectangle((x0, y, x0 + int(s * frac * 1.5), y + int(s * 0.05)),
                            radius=int(s * 0.025), fill=accent)
    return img.resize((size, size), Image.LANCZOS)
