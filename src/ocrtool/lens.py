"""Lăng kính dịch: một khung nổi trên màn hình; chữ nào lọt vào khung thì tự OCR rồi dịch sang ngôn ngữ đã chọn.

Hai cách hiện bản dịch (nút ⇅ trên thanh tiêu đề):
  * "overlay" (mặc định): bản dịch ĐÈ lên đúng chỗ chữ gốc, từng đoạn một, màu nền lấy theo ảnh, cỡ chữ tự co cho vừa.
    Trên Windows 10 (2004+)/11 các khối dịch được loại khỏi ảnh chụp màn hình và để chuột bấm/cuộn xuyên qua,
    nên lăng kính vẫn "nhìn" thấy chữ gốc bên dưới. Nơi khác: ẩn khối dịch thoáng qua mỗi lần chụp.
  * "panel": bản dịch hiện trong bảng tối bên dưới khung.

Khung được dựng bằng 4 thanh mỏng + 1 thanh tiêu đề + 1 bảng dịch (các cửa sổ Toplevel riêng), nên phần giữa
khung thật sự "rỗng": nhìn xuyên qua, bấm/cuộn xuyên qua được, và ảnh chụp vùng đó không dính khung.

Vòng lặp: mỗi `interval_ms` chụp vùng giữa khung -> so với lần trước bằng ảnh thu nhỏ -> khi nội dung đã đổi rồi
đứng yên (bạn lướt xong) mới OCR -> chữ khác lần trước thì dịch -> hiện ở bảng dịch.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk

import time
import tkinter.font as tkfont

from . import translate as tr
from .menu import MenuItem, PopupMenu
from .textutil import has_cjk
from .uiutil import THEME, WIN, clamp_pos, click_through, exclude_from_capture, font, scale, virtual_screen

MIN_W, MIN_H = 80, 28
CHANGE_THRESHOLD = 3.0        # chênh lệch trung bình (0..255) của ảnh thu nhỏ để coi là "đã đổi"


def signature(img) -> bytes:
    """Ảnh thu nhỏ xám 48x16 để so khác nhau rất nhanh."""
    return img.convert("L").resize((48, 16)).tobytes()


def sig_diff(a: bytes | None, b: bytes | None) -> float:
    if a is None or b is None or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _bbox(box):
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def _join(a: str, b: str) -> str:
    if not a:
        return b
    return a + b if (has_cjk(a[-1:]) or has_cjk(b[:1])) else a + " " + b


def group_blocks(lines: list[dict]) -> list[dict]:
    """Gom các dòng OCR (dict có 'text', 'box') thành đoạn để dịch theo ngữ cảnh và vẽ đè đúng chỗ.

    Dòng sau thuộc cùng đoạn nếu: khoảng cách dọc nhỏ (< 0,6 chiều cao dòng), chiều cao tương tự, và chồng lên
    nhau theo chiều ngang. Trả về [{'text', 'rect': (x0, y0, x1, y1), 'line_h'}] theo thứ tự đọc.
    """
    items = []
    for ln in lines:
        t = " ".join(str(ln.get("text", "")).split())
        if t and ln.get("box"):
            x0, y0, x1, y1 = _bbox(ln["box"])
            items.append((y0, x0, x1, y1, t))
    items.sort()
    blocks: list[dict] = []
    for y0, x0, x1, y1, t in items:
        h = max(1.0, y1 - y0)
        for b in reversed(blocks[-3:]):
            bx0, by0, bx1, by1 = b["rect"]
            lh = b["line_h"]
            gap = y0 - by1
            overlap = min(x1, bx1) - max(x0, bx0)
            if -0.5 * lh <= gap < 0.6 * lh and 0.75 < h / lh < 1.33 and overlap > 0.2 * min(x1 - x0, bx1 - bx0):
                b["text"] = _join(b["text"], t)
                b["rect"] = (min(bx0, x0), by0, max(bx1, x1), max(by1, y1))
                b["n"] += 1
                b["line_h"] = (lh * (b["n"] - 1) + h) / b["n"]
                break
        else:
            blocks.append({"text": t, "rect": (x0, y0, x1, y1), "line_h": h, "n": 1})
    return blocks


def colors_for(img, rect) -> tuple[str, str]:
    """(màu nền, màu chữ) cho khối dịch: nền = trung vị viền vùng chữ trong ảnh, chữ = đen/trắng tương phản."""
    x0, y0, x1, y1 = (int(v) for v in rect)
    w, h = img.size
    x0, y0, x1, y1 = max(0, x0 - 2), max(0, y0 - 2), min(w - 1, x1 + 2), min(h - 1, y1 + 2)
    px = img.load()
    samples = []
    for x in range(x0, x1 + 1, max(1, (x1 - x0) // 24)):
        samples += [px[x, y0], px[x, y1]]
    for y in range(y0, y1 + 1, max(1, (y1 - y0) // 8)):
        samples += [px[x0, y], px[x1, y]]
    if not samples:
        return "#ffffff", "#000000"
    rgb = [sorted(c[i] for c in samples)[len(samples) // 2] for i in range(3)]
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return "#%02x%02x%02x" % tuple(rgb), ("#111111" if lum > 140 else "#f5f5f5")


def wrap_text(text: str, width: int, measure) -> list[str]:
    """Ngắt dòng theo độ rộng pixel; chữ Hán/từ quá dài thì ngắt theo ký tự."""
    out, cur = [], ""
    tokens = []
    for word in text.split(" "):
        if measure(word) > width or has_cjk(word):
            tokens += list(word) + [" "]
        else:
            tokens += [word, " "]
    for tok in tokens:
        cand = cur + tok
        if cur and measure(cand.rstrip()) > width:
            out.append(cur.rstrip())
            cur = tok.lstrip()
        else:
            cur = cand
    if cur.strip():
        out.append(cur.rstrip())
    return out or [""]


def fit_text(text: str, w: int, h: int, start_px: int, make_font, min_px: int = 8):
    """Chọn cỡ chữ lớn nhất (<= start_px) để `text` ngắt dòng vừa khung w x h. Trả về (font, các dòng, cao)."""
    size = max(min_px, start_px)
    while True:
        f = make_font(size)
        lines = wrap_text(text, max(10, w), f.measure)
        total = len(lines) * f.metrics("linespace")
        if total <= h or size <= min_px:
            return f, lines, total
        size -= 1


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
        self.mode = cfg.lens_mode if cfg.lens_mode in ("overlay", "panel") else "overlay"
        self.blocks: list[dict] = []           # đoạn chữ gốc lần đọc gần nhất (toạ độ trong ảnh)
        self.block_wins: list = []             # cửa sổ khối dịch đang vẽ đè
        self.capture_safe: bool | None = None  # khối dịch có được loại khỏi ảnh chụp không
        self._fonts: dict = {}
        self._last_img = None
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
        title = self.title_lbl = tk.Label(self.top, text="⠿ Lăng kính dịch", bg=t["accent_bg"], fg="white", font=font(9, bold=True),
                         cursor="fleur", padx=px(6))
        title.pack(side="left", fill="y")
        for wdg in (self.top, title):
            wdg.bind("<ButtonPress-1>", self._move_start)
            wdg.bind("<B1-Motion>", self._move)
            wdg.bind("<ButtonRelease-1>", self._drag_end)
        self.btn_close = self._button("✕", self.close, "Đóng lăng kính")
        self.btn_pause = self._button("⏸", self.toggle_pause, "Tạm dừng")
        self.btn_copy = self._button("⧉", self.copy_translation, "Chép bản dịch")
        self.btn_mode = self._button("⇅", self.toggle_mode, "Đè lên chữ / bảng bên dưới")
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
        self._apply_mode()
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
        if self.mode == "overlay":
            self.panel.withdraw()
            return
        self.panel.deiconify()
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
        self.clear_overlay()
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
        self.clear_overlay()
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
        img = self._grab()
        sig = signature(img)
        moving = sig_diff(sig, self.last_sig) > CHANGE_THRESHOLD
        self.last_sig = sig
        if moving:
            self.dirty = True
            if self.done_sig is not None and sig_diff(sig, self.done_sig) > CHANGE_THRESHOLD:
                self.clear_overlay()                  # nội dung đã trôi: bỏ bản dịch cũ, hiện chữ gốc
            return                                     # đợi đứng yên rồi mới đọc
        if not self.dirty and sig_diff(sig, self.done_sig) <= CHANGE_THRESHOLD:
            return
        self.dirty = False
        self.done_sig = sig
        self._last_img = img
        self.ocr_pending = True
        self._req += 1
        req = self._req
        self.set_status("Đang đọc chữ…")
        self.ocr_fn(img, lambda lines, err: self._q.put(("ocr", req, lines, err)))

    def _grab(self):
        """Chụp vùng nhìn. Nếu khối dịch có thể lọt vào ảnh (không phải Windows mới), ẩn chúng thoáng qua."""
        hide = bool(self.block_wins) and not self.capture_safe
        if hide:
            for w in self.block_wins:
                w.withdraw()
            self.root.update()                 # đẩy lệnh ẩn tới màn hình ngay
            time.sleep(0.06)
        try:
            return self.grab_fn(self.rect())
        finally:
            if hide:
                for w in self.block_wins:
                    w.deiconify()

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

    def _on_ocr(self, lines, err) -> None:
        if err:
            self.set_status(str(err).strip().splitlines()[-1][:160], err=True)
            return
        blocks = group_blocks(lines or [])
        text = "\n".join(b["text"] for b in blocks)
        if not text.strip():
            self.source_text, self.blocks = "", []
            self.clear_overlay()
            self.set_status("Không thấy chữ trong khung")
            return
        if text == self.source_text and self.translated:
            self.set_status(self._done_status())
            if self.mode == "overlay" and not self.block_wins:
                self.draw_overlay()
            return
        self.source_text, self.blocks = text, blocks
        self._translate()

    def _translate(self) -> None:
        text, req = self.source_text, self._req
        paras = [b["text"] for b in self.blocks] or [text]
        target = tr.effective_target(text, self.cfg.target_lang)
        self.src_lbl.configure(text=_short(text, 160))
        self.set_status(f"Đang dịch sang {tr.lang_name(target)}…")

        def work():
            try:
                res = self.translate_fn("\n".join(paras), target)
                parts = res.text.split("\n")
                if len(parts) != len(paras):          # dịch vụ gộp/tách dòng: dịch lại từng đoạn
                    parts = [self.translate_fn(p, target).text for p in paras]
                self._q.put(("tr", req, (res, target, parts), None))
            except Exception as exc:  # noqa: BLE001
                self._q.put(("tr", req, None, exc))

        threading.Thread(target=work, name="lens-translate", daemon=True).start()

    def _on_translation(self, data, err) -> None:
        if err is not None:
            self.set_status(str(err) if isinstance(err, tr.TranslateError) else f"Lỗi dịch: {err}", err=True)
            return
        result, target, parts = data
        self.parts_tr = parts
        self.translated = "\n".join(parts)
        self.out_lbl.configure(text=self.translated)
        self._last_status = (f"{tr.lang_name(result.source) if result.source else '?'} → {tr.lang_name(target)}")
        self.set_status(self._done_status())
        if self.mode == "overlay":
            self.draw_overlay()
        else:
            self._layout_panel()

    # ------------------------------------------------------------ vẽ đè bản dịch lên chữ gốc
    def _font(self, px: int):
        f = self._fonts.get(px)
        if f is None:
            fam = font(10)[0]
            f = self._fonts[px] = tkfont.Font(root=self.root, family=fam, size=-px)
        return f

    def clear_overlay(self) -> None:
        for w in self.block_wins:
            try:
                w.destroy()
            except Exception:
                pass
        self.block_wins = []

    def draw_overlay(self) -> None:
        """Mỗi đoạn một cửa sổ nhỏ phủ đúng chỗ chữ gốc (nên phần còn lại vẫn nhìn xuyên qua được)."""
        self.clear_overlay()
        parts = getattr(self, "parts_tr", None)
        if self.closed or self.mode != "overlay" or not parts or self._last_img is None:
            return
        for b, txt in zip(self.blocks, parts):
            if not txt.strip():
                continue
            x0, y0, x1, y1 = b["rect"]
            px_, py_ = max(3, int(0.2 * b["line_h"])), max(3, int(0.3 * b["line_h"]))   # che cả dấu, đuôi chữ
            x0, y0 = max(0, int(x0) - px_), max(0, int(y0) - py_)
            x1, y1 = min(self.w, int(x1) + px_), min(self.h, int(y1) + py_)
            w, h = max(12, x1 - x0), max(10, y1 - y0)
            bg, fg = colors_for(self._last_img, b["rect"])
            f, lines, total = fit_text(txt, w - 4, h, int(b["line_h"] * 0.8), self._font)
            h = min(max(h, total + 2), self.h - y0)         # chữ quá dài: cho khối dài xuống (trong khung)
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            try:
                win.attributes("-topmost", True)
                if WIN:
                    win.attributes("-alpha", 0.97)           # cần cho click-through
            except Exception:
                pass
            win.geometry(f"{w}x{h}+{self.x + x0}+{self.y + y0}")
            cv = tk.Canvas(win, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
            cv.pack()
            cv.create_text(2, max(0, (h - total) // 2), anchor="nw", text="\n".join(lines), font=f, fill=fg)
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Button-1>"):
                cv.bind(ev, lambda e: self.clear_overlay())   # nơi không bấm xuyên được: chạm vào là ẩn
            win.update_idletasks()
            safe = exclude_from_capture(win)
            click_through(win)
            self.capture_safe = safe if self.capture_safe is None else (self.capture_safe and safe)
            self.block_wins.append(win)
        for p in (self.top, self.left, self.right, self.bottom, self.grip):
            try:
                p.lift()
            except Exception:
                pass

    def toggle_mode(self) -> None:
        self.mode = "panel" if self.mode == "overlay" else "overlay"
        self.cfg.lens_mode = self.mode
        self.save_cfg()
        self._apply_mode()

    def _apply_mode(self) -> None:
        if self.mode == "overlay":
            self.panel.withdraw()
            if self.translated:
                self.draw_overlay()
        else:
            self.clear_overlay()
            self._layout_panel()

    def _done_status(self) -> str:
        return getattr(self, "_last_status", "") + ("   •   ⏸ đang tạm dừng" if self.paused else "")

    def set_status(self, msg: str, err: bool = False) -> None:
        self.status.configure(text=msg, fg="#f87171" if err else THEME["dim"])
        self.title_lbl.configure(text="⠿ " + (_short(msg, 48) if msg else "Lăng kính dịch"),
                                 fg="#fecaca" if err else "white")

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
        self.clear_overlay()
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
