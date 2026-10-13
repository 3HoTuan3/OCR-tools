"""Tiện ích giao diện Tk dùng chung: bảng màu, font, tỉ lệ DPI, màn hình ảo, nhận biết nút chuột."""
from __future__ import annotations

import sys
import time

THEME = {
    "bg": "#2b2b2b", "panel": "#202020", "hover": "#3d3d3d", "fg": "#f2f2f2", "dim": "#7d7d7d",
    "sep": "#454545", "border": "#505050", "accent": "#60a5fa", "accent_bg": "#1d4ed8", "input": "#1b1b1b",
}
WIN = sys.platform == "win32"


_photo_cache: dict = {}


def tk_icon(root, name: str, px: int, color: str = THEME["fg"]):
    """PhotoImage của icon asset (đã tô màu), giữ trong bộ nhớ đệm; None nếu không có icon."""
    from .icons import has_icon, icon_image

    if not has_icon(name):
        return None
    key = (id(root), name, px, color)
    img = _photo_cache.get(key)
    if img is None:
        from PIL import ImageTk

        img = _photo_cache[key] = ImageTk.PhotoImage(icon_image(name, px, color), master=root)
    return img


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


def set_app_icons(root) -> None:
    """Logo app cho mọi cửa sổ Tk (thanh tiêu đề, Alt+Tab, taskbar)."""
    from .icons import asset, logo

    try:
        from PIL import ImageTk

        imgs = [ImageTk.PhotoImage(logo(s), master=root) for s in (16, 32, 48, 64) if logo(s) is not None]
        if imgs:
            root.iconphoto(True, *imgs)
            root._app_icons = imgs
        if WIN and asset("app.ico").exists():
            root.iconbitmap(default=str(asset("app.ico")))
    except Exception:
        pass


def set_app_id() -> None:
    """Windows: tách app khỏi nhóm "Python" trên taskbar để hiện đúng logo. Gọi trước khi tạo cửa sổ."""
    if not WIN:
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ocrtool.tray")
    except Exception:
        pass


# ---------------------------------------------------------------- Windows: cửa sổ phủ của lăng kính
def _hwnd(win):
    import ctypes

    win.update_idletasks()
    return ctypes.windll.user32.GetAncestor(win.winfo_id(), 2)      # GA_ROOT


def exclude_from_capture(win) -> bool:
    """Windows 10 2004+: cửa sổ vẫn hiện trên màn hình nhưng KHÔNG lọt vào ảnh chụp màn hình
    (nên lăng kính vẫn đọc được chữ gốc nằm bên dưới bản dịch). Trả về False nếu không hỗ trợ."""
    if not WIN:
        return False
    try:
        import ctypes

        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(_hwnd(win), 0x11))  # WDA_EXCLUDEFROMCAPTURE
    except Exception:
        return False


def click_through(win) -> bool:
    """Windows: chuột bấm/cuộn xuyên qua cửa sổ (WS_EX_TRANSPARENT). Cần gọi sau khi đã đặt -alpha."""
    if not WIN:
        return False
    try:
        import ctypes

        u = ctypes.windll.user32
        h = _hwnd(win)
        style = u.GetWindowLongW(h, -20)                            # GWL_EXSTYLE
        u.SetWindowLongW(h, -20, style | 0x80000 | 0x20 | 0x08000000)  # LAYERED | TRANSPARENT | NOACTIVATE
        return True
    except Exception:
        return False
