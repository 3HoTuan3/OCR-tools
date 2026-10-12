"""Chọn vùng màn hình: chụp cả màn hình rồi hiện lớp phủ để kéo chọn (giống Snipping Tool).

App nền dùng `open_selector` (chạy ngay trong Tk của app, hiện tức thì); `ocrtool.job` dùng `select_region`.
"""
from __future__ import annotations

import sys

from PIL import Image

MIN_SIZE = 5  # vùng chọn nhỏ hơn 5px coi như bấm nhầm


class SnipError(RuntimeError):
    pass


def set_dpi_aware() -> None:
    """Windows: để toạ độ Tk bằng điểm ảnh thật (khớp với ảnh chụp), kể cả nhiều màn hình khác tỉ lệ."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def grab_virtual_screen() -> tuple[Image.Image, dict]:
    """Chụp toàn bộ màn hình ảo (mọi màn hình). Trả về (ảnh, {'left','top','width','height'})."""
    try:
        import mss

        with mss.mss() as sct:
            mon = dict(sct.monitors[0])
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img, mon
    except Exception as exc:
        raise SnipError(f"Không chụp được màn hình: {exc}") from exc


def norm_rect(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def dim_rects(sel, w: int, h: int) -> list[tuple[int, int, int, int]]:
    """Luôn trả về đúng 4 hình chữ nhật phủ phần NGOÀI vùng chọn để làm tối
    (chưa chọn: hình đầu phủ cả màn hình, ba hình còn lại rỗng)."""
    if sel is None:
        return [(0, 0, w, h), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)]
    l, t, r, b = sel
    return [(0, 0, w, t), (0, b, w, h), (0, t, l, b), (r, t, w, b)]


def build_selector(win, tk, ImageTk, full: Image.Image, mon: dict, finish) -> None:
    """Dựng lớp phủ chọn vùng trên cửa sổ `win` (Tk hoặc Toplevel). Gọi finish(rect) / finish(None) đúng một lần."""
    w, h = mon["width"], mon["height"]
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.geometry(f"{w}x{h}+{mon['left']}+{mon['top']}")
    canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0, bd=0, cursor="crosshair")
    canvas.pack()
    photo = ImageTk.PhotoImage(full, master=win)
    canvas._photo = photo                      # giữ tham chiếu, nếu không ảnh biến mất
    canvas.create_image(0, 0, image=photo, anchor="nw")

    dims = [canvas.create_rectangle(*r, fill="black", stipple="gray50", outline="")
            for r in dim_rects(None, w, h)]
    border = canvas.create_rectangle(0, 0, 0, 0, outline="#2f9bff", width=2, state="hidden")
    canvas.create_rectangle(w // 2 - 230, 14, w // 2 + 230, 50, fill="#111827", outline="")
    canvas.create_text(w // 2, 32, fill="white", font=("Segoe UI", 12),
                       text="Kéo chuột để chọn vùng chữ   •   Esc hoặc chuột phải để huỷ")
    size_bg = canvas.create_rectangle(0, 0, 0, 0, fill="#111827", outline="", state="hidden")
    size_txt = canvas.create_text(0, 0, fill="white", font=("Segoe UI", 10), state="hidden", anchor="nw")

    state = {"start": None, "sel": None, "done": False}

    def refresh(sel):
        for item, rect in zip(dims, dim_rects(sel, w, h)):
            canvas.coords(item, *rect)
        if sel is None:
            canvas.itemconfigure(border, state="hidden")
            canvas.itemconfigure(size_bg, state="hidden")
            canvas.itemconfigure(size_txt, state="hidden")
            return
        l, t, r, b = sel
        canvas.coords(border, l, t, r, b)
        canvas.itemconfigure(border, state="normal")
        label = f"{r - l} × {b - t}"
        ty = t - 26 if t > 30 else b + 6
        canvas.coords(size_txt, l + 6, ty + 3)
        canvas.itemconfigure(size_txt, text=label, state="normal")
        canvas.coords(size_bg, l, ty, l + 12 * len(label) + 4, ty + 22)
        canvas.itemconfigure(size_bg, state="normal")
        canvas.tag_raise(size_bg)
        canvas.tag_raise(size_txt)

    def done(rect):
        if state["done"]:
            return
        state["done"] = True
        finish(rect)

    def on_press(e):
        state["start"] = (e.x, e.y)

    def on_drag(e):
        if state["start"]:
            state["sel"] = norm_rect(*state["start"], e.x, e.y)
            refresh(state["sel"])

    def on_release(e):
        rect = None
        if state["start"]:
            l, t, r, b = norm_rect(*state["start"], e.x, e.y)
            l, t, r, b = max(l, 0), max(t, 0), min(r, w), min(b, h)
            if r - l >= MIN_SIZE and b - t >= MIN_SIZE:
                rect = (l, t, r, b)
        done(rect)

    def cancel(_e=None):
        done(None)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<Button-3>", cancel)
    win.bind("<Escape>", cancel)
    win.update_idletasks()
    win.focus_force()
    win.lift()


def select_region(full: Image.Image, mon: dict) -> Image.Image | None:
    """Hiện lớp phủ toàn màn hình (Tk riêng, chặn tới khi xong); trả về ảnh vùng đã chọn hoặc None nếu huỷ."""
    import tkinter as tk

    from PIL import ImageTk

    root = tk.Tk()
    box: dict = {"rect": None}

    def finish(rect):
        box["rect"] = rect
        root.destroy()

    build_selector(root, tk, ImageTk, full, mon, finish)
    root.mainloop()
    return full.crop(box["rect"]) if box["rect"] else None


def open_selector(master, full: Image.Image, mon: dict, on_done):
    """Lớp phủ chọn vùng trên Tk đang chạy của app (không chặn, hiện tức thì). on_done(ảnh | None)."""
    import tkinter as tk

    from PIL import ImageTk

    win = tk.Toplevel(master)

    def finish(rect):
        try:
            win.destroy()
        finally:
            on_done(full.crop(rect) if rect else None)

    build_selector(win, tk, ImageTk, full, mon, finish)
    return win


def snip_screen(delay_s: float = 0.0) -> Image.Image | None:
    """Tiện ích: chụp màn hình + chọn vùng. Trả về ảnh vùng chọn hoặc None nếu huỷ."""
    import time

    set_dpi_aware()
    try:
        import tkinter  # noqa: F401  (kiểm tra sớm)
    except ImportError as exc:
        raise SnipError("Thiếu tkinter. Linux: sudo apt install python3-tk") from exc
    if delay_s > 0:
        time.sleep(delay_s)
    full, mon = grab_virtual_screen()
    return select_region(full, mon)
