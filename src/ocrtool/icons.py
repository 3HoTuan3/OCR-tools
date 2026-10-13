"""Biểu tượng của app: logo (assets/app*.png, app.ico), icon menu/nút (assets/icons/*.png, Fluent UI, MIT).

Nếu thiếu file asset thì vẽ tạm bằng Pillow như bản cũ, để app vẫn chạy.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"


def asset(name: str) -> Path:
    return ASSETS / name


def has_icon(name: str) -> bool:
    return bool(name) and (ASSETS / "icons" / f"{name}.png").exists()


@lru_cache(maxsize=256)
def icon_image(name: str, px: int, color: str = "#f2f2f2"):
    """Icon menu/nút cỡ px, tô màu `color` (icon gốc màu trắng, giữ kênh alpha)."""
    from PIL import Image

    src = Image.open(ASSETS / "icons" / f"{name}.png").convert("RGBA").resize((px, px), Image.LANCZOS)
    c = color.lstrip("#")
    rgb = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    out = Image.new("RGBA", src.size, rgb + (0,))
    out.putalpha(src.getchannel("A"))
    return out


def logo(size: int):
    """Logo app cỡ `size` (lấy file gần nhất rồi thu nhỏ cho nét)."""
    from PIL import Image

    for s in (16, 24, 32, 48, 64):
        if size <= s and (ASSETS / f"app_{s}.png").exists():
            im = Image.open(ASSETS / f"app_{s}.png").convert("RGBA")
            return im if s == size else im.resize((size, size), Image.LANCZOS)
    p = ASSETS / "app.png"
    if p.exists():
        return Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    return None

TILE = {"idle": (43, 45, 49), "hover": (62, 65, 72), "busy": (37, 99, 235)}
ACCENT = (96, 165, 250)


def make_icon_image(size: int = 64):
    """Biểu tượng khay hệ thống (logo app)."""
    im = logo(size)
    if im is not None:
        return im
    return _drawn_icon(size)


def _drawn_icon(size: int = 64):
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
    """Ô nổi: logo app; rê chuột = sáng hơn; đang xử lý = tối đi + ba chấm."""
    from PIL import Image, ImageDraw, ImageEnhance

    im = logo(size)
    if im is None:
        return _drawn_tile(size, state)
    if state == "hover":
        rgb = ImageEnhance.Brightness(im.convert("RGB")).enhance(1.18)
        rgb.putalpha(im.getchannel("A"))
        return rgb
    if state == "busy":
        k = 4
        big = im.resize((size * k, size * k), Image.LANCZOS)
        shade = Image.new("RGBA", big.size, (15, 23, 42, 150))
        shade.putalpha(Image.eval(big.getchannel("A"), lambda a: a * 150 // 255))
        big = Image.alpha_composite(big, shade)
        d = ImageDraw.Draw(big)
        r = size * k * 0.07
        for i in (-1, 0, 1):
            cx, cy = size * k / 2 + i * size * k * 0.2, size * k / 2
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
        return big.resize((size, size), Image.LANCZOS)
    return im


def _drawn_tile(size: int, state: str = "idle"):
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
