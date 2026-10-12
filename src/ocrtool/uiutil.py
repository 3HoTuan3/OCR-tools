"""Tiện ích giao diện Tk dùng chung: bảng màu, font, tỉ lệ DPI, màn hình ảo, nhận biết nút chuột."""
from __future__ import annotations

import sys
import time

THEME = {
    "bg": "#2b2b2b", "panel": "#202020", "hover": "#3d3d3d", "fg": "#f2f2f2", "dim": "#7d7d7d",
    "sep": "#454545", "border": "#505050", "accent": "#60a5fa", "accent_bg": "#1d4ed8", "input": "#1b1b1b",
}
WIN = sys.platform == "win32"


def font(size: int = 10, bold: bool = False, symbol: bool = False):
    family = ("Segoe UI Symbol" if symbol else "Segoe UI") if WIN else "DejaVu Sans"
    return (family, size, "bold") if bold else (family, size)


def scale(root) -> float:
    """Hệ số DPI so với 96 (1.0 = 100%)."""
    try:
        return max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
    except Exception:
        return 1.0


def virtual_screen(root) -> tuple[int, int, int, int]:
    """(x, y, rộng, cao) của toàn bộ màn hình ảo."""
    if WIN:
        try:
            import ctypes

            g = ctypes.windll.user32.GetSystemMetrics
            w, h = g(78), g(79)
            if w > 0 and h > 0:
                return g(76), g(77), w, h
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def clamp_pos(x: int, y: int, w: int, h: int, bounds, margin: int = 0) -> tuple[int, int]:
    bx, by, bw, bh = bounds
    x = max(bx + margin, min(x, bx + bw - w - margin))
    y = max(by + margin, min(y, by + bh - h - margin))
    return x, y


def button_down() -> bool:
    """Có nút chuột nào đang giữ không (chỉ Windows; nơi khác luôn False)."""
    if not WIN:
        return False
    try:
        import ctypes

        gk = ctypes.windll.user32.GetAsyncKeyState
        return any(gk(vk) & 0x8000 for vk in (0x01, 0x02, 0x04))
    except Exception:
        return False


def now() -> float:
    return time.monotonic()
