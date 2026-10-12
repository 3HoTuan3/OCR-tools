"""Cửa sổ nổi nhỏ (ô vuông bo góc, luôn trên cùng): bấm trái = chụp, bấm phải = menu, kéo = di chuyển."""
from __future__ import annotations

import tkinter as tk

from .icons import make_tile
from .uiutil import THEME, WIN, clamp_pos, font, scale, virtual_screen

KEY = "#010203"            # màu "trong suốt" (Windows) cho phần góc bo tròn
DRAG_PX = 4


class FloatingButton:
    def __init__(self, root, cfg, on_click, on_menu, on_moved):
        self.root, self.cfg = root, cfg
        self.on_click, self.on_menu, self.on_moved = on_click, on_menu, on_moved
        self.state = "idle"
        self._press = None
        self._dragging = False
        self._last = (0, 0)
        self._hover = False
        self._imgs: dict = {}
        self.s = scale(root)

        root.overrideredirect(True)
        root.title("OCR")
        if WIN:
            try:
                root.wm_attributes("-transparentcolor", KEY)
            except Exception:
                pass
        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, bg=KEY if WIN else THEME["bg"],
                                cursor="hand2")
        self.canvas.pack()
        self._item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", lambda e: self.on_menu(e.x_root, e.y_root))
        self.canvas.bind("<Enter>", lambda e: self._set_hover(True))
        self.canvas.bind("<Leave>", lambda e: self._set_hover(False))
        self.apply_size()
        self.apply_topmost()
        self.place(cfg.float_x, cfg.float_y)
        self._keep_on_top()

    # ------------------------------------------------------------ hiển thị
    @property
    def size(self) -> int:
        return max(24, int(self.cfg.float_size * self.s))

    def apply_size(self) -> None:
        from PIL import ImageTk

        size = self.size
        self._imgs = {st: ImageTk.PhotoImage(make_tile(size, st), master=self.root)
                      for st in ("idle", "hover", "busy")}
        self.canvas.configure(width=size, height=size)
        self._refresh()
        self.apply_opacity()

    def _refresh(self) -> None:
        st = "busy" if self.state == "busy" else ("hover" if self._hover else "idle")
        self.canvas.itemconfigure(self._item, image=self._imgs[st])

    def set_state(self, state: str) -> None:
        self.state = state
        self._refresh()
        self.canvas.configure(cursor="watch" if state == "busy" else "hand2")

    def _set_hover(self, on: bool) -> None:
        self._hover = on
        self._refresh()
        self.apply_opacity()

    def apply_opacity(self) -> None:
        a = 1.0 if (self._hover or self.state == "busy") else max(0.3, min(1.0, float(self.cfg.float_opacity)))
        try:
            self.root.attributes("-alpha", a)
        except Exception:
            pass

    def apply_topmost(self) -> None:
        try:
            self.root.attributes("-topmost", bool(self.cfg.float_topmost))
        except Exception:
            pass

    def _keep_on_top(self) -> None:
        """Windows hay đẩy cửa sổ xuống khi có app toàn màn hình/taskbar bật lên: nhắc lại định kỳ."""
        try:
            if self.cfg.float_topmost and self.root.state() != "withdrawn":
                self.root.attributes("-topmost", True)
                self.root.lift()
            self.root.after(3000, self._keep_on_top)
        except Exception:
            pass

    # ------------------------------------------------------------ vị trí
    def place(self, x: int, y: int) -> None:
        size = self.size
        bounds = virtual_screen(self.root)
        if x < 0 or y < 0:                                   # mặc định: góc dưới phải, trên thanh taskbar
            x = bounds[0] + bounds[2] - size - int(24 * self.s)
            y = bounds[1] + bounds[3] - size - int(100 * self.s)
        x, y = clamp_pos(x, y, size, size, bounds, margin=0)
        self.root.geometry(f"{size}x{size}+{x}+{y}")

    def position(self) -> tuple[int, int]:
        return self.root.winfo_x(), self.root.winfo_y()

    def show(self) -> None:
        self.root.deiconify()
        self.apply_topmost()
        self.root.lift()

    def hide(self) -> None:
        self.root.withdraw()

    @property
    def visible(self) -> bool:
        return self.root.state() != "withdrawn"

    # ------------------------------------------------------------ chuột
    def _on_press(self, e) -> None:
        self._press = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y())
        self._dragging = False

    def _on_motion(self, e) -> None:
        if not self._press:
            return
        x0, y0, wx, wy = self._press
        dx, dy = e.x_root - x0, e.y_root - y0
        if not self._dragging and max(abs(dx), abs(dy)) < DRAG_PX:
            return
        self._dragging = True
        size = self.size
        nx, ny = clamp_pos(wx + dx, wy + dy, size, size, virtual_screen(self.root))
        self._last = (nx, ny)
        self.root.geometry(f"+{nx}+{ny}")

    def _on_release(self, e) -> None:
        was_drag, self._press = self._dragging, None
        self._dragging = False
        if was_drag:
            self.on_moved(*self._last)
        elif 0 <= e.x < self.size and 0 <= e.y < self.size:
            self.on_click()


def show_toast(root, message: str, ms: int = 2200, near: tuple[int, int] | None = None):
    """Thông báo nhỏ tự tắt (không cần khay hệ thống, không cướp focus)."""
    s = scale(root)
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    tk.Label(win, text=message, bg="#1f2937", fg="white", padx=int(16 * s), pady=int(9 * s),
             font=font(10), justify="left", wraplength=int(380 * s)).pack()
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    bounds = virtual_screen(root)
    if near is not None:
        x, y = near[0] - w, near[1] - h - int(8 * s)
    else:
        x, y = bounds[0] + bounds[2] - w - int(24 * s), bounds[1] + bounds[3] - h - int(80 * s)
    x, y = clamp_pos(x, y, w, h, bounds, margin=int(8 * s))
    win.geometry(f"+{x}+{y}")
    win.after(ms, win.destroy)
    return win
