"""Lăng kính dịch: một khung nổi trên màn hình; chữ nào lọt vào khung thì tự OCR rồi dịch sang ngôn ngữ đã chọn.

Khung được dựng bằng 4 thanh mỏng + 1 thanh tiêu đề + 1 bảng dịch (các cửa sổ Toplevel riêng), nên phần giữa
khung thật sự "rỗng": nhìn xuyên qua, bấm/cuộn xuyên qua được, và ảnh chụp vùng đó không dính khung.

Vòng lặp: mỗi `interval_ms` chụp vùng giữa khung -> so với lần trước bằng ảnh thu nhỏ -> khi nội dung đã đổi rồi
đứng yên (bạn lướt xong) mới OCR -> chữ khác lần trước thì dịch -> hiện ở bảng dịch.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk

from . import translate as tr
from .menu import MenuItem, PopupMenu
from .uiutil import THEME, clamp_pos, font, scale, virtual_screen

MIN_W, MIN_H = 80, 28
CHANGE_THRESHOLD = 3.0        # chênh lệch trung bình (0..255) của ảnh thu nhỏ để coi là "đã đổi"


def signature(img) -> bytes:
    """Ảnh thu nhỏ xám 48x16 để so khác nhau rất nhanh."""
    return img.convert("L").resize((48, 16)).tobytes()


def sig_diff(a: bytes | None, b: bytes | None) -> float:
    if a is None or b is None or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def grab_rect(rect):
    """Chụp vùng (x, y, w, h) trên màn hình -> PIL.Image."""
    import mss
    from PIL import Image

    x, y, w, h = rect
    with mss.mss() as sct:
        shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class LensWindow:
    """ocr_fn(img, cb(lines|None, error|None)); translate_fn(text, target) -> Translation; copy_fn(text)."""

    def __init__(self, root, cfg, ocr_fn, translate_fn, copy_fn, save_cfg=lambda: None,
                 grab_fn=grab_rect, on_close=None, interval_ms: int = 400):
        self.root, self.cfg = root, cfg
        self.ocr_fn, self.translate_fn, self.copy_fn = ocr_fn, translate_fn, copy_fn
        self.save_cfg, self.grab_fn, self.on_close = save_cfg, grab_fn, on_close
        self.interval_ms = interval_ms
        self.s = scale(root)
        self.paused = False
        self.closed = False
        self.ocr_pending = False
        self.last_sig: bytes | None = None       # khung hình lần trước
        self.done_sig: bytes | None = None       # khung hình đã OCR gần nhất
        self.dirty = True
        self.source_text = ""
        self.translated = ""
        self._req = 0
        self._q: queue.Queue = queue.Queue()
        self._drag = None
        self.menu = PopupMenu(root)
        t = THEME
        px = self.px

        self.bar_h, self.edge = px(28), max(2, px(3))
        bounds = virtual_screen(root)
        w = cfg.lens_w if cfg.lens_w >= MIN_W else px(520)
        h = cfg.lens_h if cfg.lens_h >= MIN_H else px(140)
        x = cfg.lens_x if cfg.lens_x >= 0 else bounds[0] + (bounds[2] - w) // 2
        y = cfg.lens_y if cfg.lens_y >= 0 else bounds[1] + (bounds[3] - h) // 3
        x, y = clamp_pos(x, y, w, h, bounds, margin=px(4))
        self.x, self.y, self.w, self.h = x, y, w, h          # vùng "nhìn" (phần rỗng giữa khung)

        def part(bg):
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass
            win.configure(bg=bg)
            return win

        self.top = part(t["accent_bg"])
        self.left, self.right, self.bottom = part(t["accent_bg"]), part(t["accent_bg"]), part(t["accent_bg"])
        self.grip = part(t["accent"])
        self.panel = part(t["panel"])
        self.parts = [self.top, self.left, self.right, self.bottom, self.grip, self.panel]

        # thanh tiêu đề: kéo để di chuyển + nút
        title = tk.Label(self.top, text="⠿ Lăng kính dịch", bg=t["accent_bg"], fg="white", font=font(9, bold=True),
                         cursor="fleur", padx=px(6))
        title.pack(side="left", fill="y")
        for wdg in (self.top, title):
            wdg.bind("<ButtonPress-1>", self._move_start)
            wdg.bind("<B1-Motion>", self._move)
            wdg.bind("<ButtonRelease-1>", self._drag_end)
        self.btn_close = self._button("✕", self.close, "Đóng lăng kính")
        self.btn_pause = self._button("⏸", self.toggle_pause, "Tạm dừng")
        self.btn_copy = self._button("⧉", self.copy_translation, "Chép bản dịch")
        self.btn_lang = self._button("", self._pick_language, "Ngôn ngữ đích", wide=True)
        self._update_lang()

        # tay nắm đổi cỡ ở góc dưới phải
        self.grip.configure(cursor="size_nw_se" if root.tk.call("tk", "windowingsystem") == "win32" else "bottom_right_corner")
        self.grip.bind("<ButtonPress-1>", self._resize_start)
        self.grip.bind("<B1-Motion>", self._resize)
        self.grip.bind("<ButtonRelease-1>", self._drag_end)

        # bảng dịch
        self.src_lbl = tk.Label(self.panel, text="", bg=t["panel"], fg=t["dim"], font=font(9), anchor="w",
                                justify="left")
        self.src_lbl.pack(fill="x", padx=px(10), pady=(px(6), 0))
        self.out_lbl = tk.Label(self.panel, text="Đưa chữ vào trong khung…", bg=t["panel"], fg=t["fg"],
                                font=font(11), anchor="w", justify="left")
        self.out_lbl.pack(fill="x", padx=px(10), pady=(px(2), px(4)))
        self.status = tk.Label(self.panel, text="", bg=t["panel"], fg=t["dim"], font=font(8), anchor="w")
        self.status.pack(fill="x", padx=px(10), pady=(0, px(6)))
        for wdg in self.parts:
            wdg.bind("<Escape>", lambda e: self.close())

        self.layout()
        self.raise_()
        self.root.after(150, self._tick)
        self.root.after(80, self._drain)

    # ------------------------------------------------------------ dựng / bố cục
    def px(self, n: float) -> int:
        return max(1, int(n * self.s))

    def _button(self, text, cmd, tip, wide=False):
        t = THEME
        b = tk.Label(self.top, text=text, bg=t["accent_bg"], fg="white", font=font(10, symbol=not wide),
                     padx=self.px(8 if wide else 6), cursor="hand2")
        b.pack(side="right", fill="y")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=THEME["accent"]))
        b.bind("<Leave>", lambda e: b.configure(bg=THEME["accent_bg"]))
        return b

    def rect(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h

    def layout(self) -> None:
        x, y, w, h, e, bh = self.x, self.y, self.w, self.h, self.edge, self.bar_h
        self.top.geometry(f"{w + 2 * e}x{bh}+{x - e}+{y - bh}")
        self.left.geometry(f"{e}x{h}+{x - e}+{y}")
        self.right.geometry(f"{e}x{h}+{x + w}+{y}")
        self.bottom.geometry(f"{w + 2 * e}x{e}+{x - e}+{y + h}")
        g = self.px(12)
        self.grip.geometry(f"{g}x{g}+{x + w + e - g // 2}+{y + h + e - g // 2}")
        self._layout_panel()

    def _layout_panel(self) -> None:
        x, y, w, h, e = self.x, self.y, self.w, self.h, self.edge
        wrap = max(self.px(160), w + 2 * e - self.px(20))
        self.out_lbl.configure(wraplength=wrap)
        self.src_lbl.configure(wraplength=wrap)
        self.panel.update_idletasks()
        ph = self.panel.winfo_reqheight()
        pw = w + 2 * e
        bounds = virtual_screen(self.root)
        py = y + h + e + self.px(4)
        if py + ph > bounds[1] + bounds[3]:               # thiếu chỗ phía dưới -> đặt lên trên thanh tiêu đề
            py = y - self.bar_h - ph - self.px(4)
        self.panel.geometry(f"{pw}x{ph}+{x - e}+{max(bounds[1], py)}")

    def raise_(self) -> None:
        for p in self.parts:
            try:
                p.lift()
            except Exception:
                pass

    # ------------------------------------------------------------ kéo / đổi cỡ
    def _move_start(self, ev) -> None:
        self._drag = ("move", ev.x_root, ev.y_root, self.x, self.y, self.w, self.h)

    def _move(self, ev) -> None:
        if not self._drag or self._drag[0] != "move":
            return
        _k, x0, y0, sx, sy, w, h = self._drag
        bounds = virtual_screen(self.root)
        nx, ny = clamp_pos(sx + ev.x_root - x0, sy + ev.y_root - y0, w, h, bounds)
        ny = max(ny, bounds[1] + self.bar_h)
        self.x, self.y = nx, ny
        self.layout()

    def _resize_start(self, ev) -> None:
        self._drag = ("size", ev.x_root, ev.y_root, self.x, self.y, self.w, self.h)

    def _resize(self, ev) -> None:
        if not self._drag or self._drag[0] != "size":
            return
        _k, x0, y0, sx, sy, w, h = self._drag
        bounds = virtual_screen(self.root)
        self.w = max(MIN_W, min(w + ev.x_root - x0, bounds[0] + bounds[2] - sx - self.edge))
        self.h = max(MIN_H, min(h + ev.y_root - y0, bounds[1] + bounds[3] - sy - self.edge))
        self.layout()

    def _drag_end(self, _ev=None) -> None:
        if self._drag:
            self._drag = None
            self.cfg.lens_x, self.cfg.lens_y, self.cfg.lens_w, self.cfg.lens_h = self.x, self.y, self.w, self.h
            self.save_cfg()
            self.dirty = True

    # ------------------------------------------------------------ vòng lặp chụp -> OCR
    def _tick(self) -> None:
        if self.closed:
            return
        try:
            self.step()
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"Lỗi chụp vùng: {exc}", err=True)
        self.root.after(self.interval_ms, self._tick)

    def step(self) -> None:
        """Một nhịp: chụp, so sánh, và gửi OCR khi nội dung đã đứng yên sau khi đổi."""
        if self.paused or self._drag or self.ocr_pending:
            return
        img = self.grab_fn(self.rect())
        sig = signature(img)
        moving = sig_diff(sig, self.last_sig) > CHANGE_THRESHOLD
        self.last_sig = sig
        if moving:
            self.dirty = True
            return                                     # đợi đứng yên rồi mới đọc
        if not self.dirty and sig_diff(sig, self.done_sig) <= CHANGE_THRESHOLD:
            return
        self.dirty = False
        self.done_sig = sig
        self.ocr_pending = True
        self._req += 1
        req = self._req
        self.set_status("Đang đọc chữ…")
        self.ocr_fn(img, lambda lines, err: self._q.put(("ocr", req, lines, err)))

    def _drain(self) -> None:
        if self.closed:
            return
        try:
            while True:
                kind, req, data, err = self._q.get_nowait()
                if kind == "ocr":
                    self.ocr_pending = False
                    if req == self._req:
                        self._on_ocr(data, err)
                elif kind == "tr" and req == self._req:
                    self._on_translation(data, err)
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    def _on_ocr(self, text, err) -> None:
        if err:
            self.set_status(str(err).strip().splitlines()[-1][:160], err=True)
            return
        text = (text or "").strip()
        if not text:
            self.source_text = ""
            self.set_status("Không thấy chữ trong khung")
            return
        if text == self.source_text and self.translated:
            self.set_status(self._done_status())
            return
        self.source_text = text
        self._translate()

    def _translate(self) -> None:
        text, req = self.source_text, self._req
        target = tr.effective_target(text, self.cfg.target_lang)
        self.src_lbl.configure(text=_short(text, 160))
        self.set_status(f"Đang dịch sang {tr.lang_name(target)}…")

        def work():
            try:
                self._q.put(("tr", req, (self.translate_fn(text, target), target), None))
            except Exception as exc:  # noqa: BLE001
                self._q.put(("tr", req, None, exc))

        threading.Thread(target=work, name="lens-translate", daemon=True).start()

    def _on_translation(self, data, err) -> None:
        if err is not None:
            self.set_status(str(err) if isinstance(err, tr.TranslateError) else f"Lỗi dịch: {err}", err=True)
            return
        result, target = data
        self.translated = result.text
        self.out_lbl.configure(text=result.text)
        self._last_status = (f"{tr.lang_name(result.source) if result.source else '?'} → {tr.lang_name(target)}")
        self.set_status(self._done_status())
        self._layout_panel()

    def _done_status(self) -> str:
        return getattr(self, "_last_status", "") + ("   •   ⏸ đang tạm dừng" if self.paused else "")

    def set_status(self, msg: str, err: bool = False) -> None:
        self.status.configure(text=msg, fg="#f87171" if err else THEME["dim"])

    # ------------------------------------------------------------ nút
    def _update_lang(self) -> None:
        self.btn_lang.configure(text=f"→ {tr.lang_name(self.cfg.target_lang)} ▾")

    def _pick_language(self) -> None:
        items = [MenuItem(label=name, checked=(code == self.cfg.target_lang), action=lambda c=code: self.set_target(c))
                 for code, name in tr.LANGS.items()]
        self.menu.show(items, self.btn_lang.winfo_rootx(), self.btn_lang.winfo_rooty() + self.btn_lang.winfo_height())

    def set_target(self, code: str) -> None:
        self.cfg.target_lang = code
        self.save_cfg()
        self._update_lang()
        self.dirty = True
        if self.source_text:
            self._req += 1
            self._translate()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.btn_pause.configure(text="▶" if self.paused else "⏸")
        self.set_status("⏸ Đã tạm dừng — bấm ▶ để tiếp tục" if self.paused else "Tiếp tục theo dõi khung…")
        if not self.paused:
            self.dirty = True

    def copy_translation(self) -> None:
        if self.translated:
            try:
                self.copy_fn(self.translated)
                self.set_status(f"Đã chép bản dịch ({len(self.translated)} ký tự)")
            except Exception as exc:  # noqa: BLE001
                self.set_status(str(exc), err=True)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.menu.close()
        for p in self.parts:
            try:
                p.destroy()
            except Exception:
                pass
        if self.on_close:
            self.on_close(self)


def _short(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"
