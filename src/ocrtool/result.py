"""Cửa sổ kết quả sau khi chụp: tab "Bắt chữ" (chữ gốc, sửa được) và tab "Dịch" (chọn ngôn ngữ đích)."""
from __future__ import annotations

import queue
import threading
import tkinter as tk

from . import translate as tr
from .menu import MenuItem, PopupMenu
from .uiutil import THEME, clamp_pos, font, scale, virtual_screen


class ResultWindow:
    """translate_fn(text, target) -> Translation (chạy ở luồng nền); copy_fn(text) chép vào clipboard."""

    def __init__(self, root, text: str, cfg, translate_fn, copy_fn, save_cfg=lambda: None,
                 start_tab: str = "orig", near=None, on_close=None):
        self.root, self.cfg = root, cfg
        self.translate_fn, self.copy_fn, self.save_cfg = translate_fn, copy_fn, save_cfg
        self.on_close = on_close
        self.s = scale(root)
        self.orig = text
        self.trans: str | None = None
        self.trans_key = None                      # (text, target) đã dịch
        self.tab = None
        self.target = tr.effective_target(text, cfg.target_lang)
        self._explicit = False
        self._req = 0
        self._q: queue.Queue = queue.Queue()
        self._closed = False
        self.menu = PopupMenu(root)

        t = THEME
        win = self.win = tk.Toplevel(root)
        win.title("OCR – kết quả")
        win.configure(bg=t["panel"])
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda e: self.close())

        px = lambda n: int(n * self.s)  # noqa: E731
        bar = tk.Frame(win, bg=t["bg"])
        bar.pack(fill="x")
        self.tab_btns = {}
        for key, label in (("orig", "Bắt chữ"), ("trans", "Dịch")):
            b = tk.Label(bar, text=label, bg=t["bg"], fg=t["dim"], font=font(10, bold=True),
                         padx=px(16), pady=px(9), cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            self.tab_btns[key] = b
        self.lang_btn = tk.Label(bar, text="", bg=t["bg"], fg=t["accent"], font=font(10), padx=px(12),
                                 pady=px(9), cursor="hand2")
        self.lang_btn.bind("<Button-1>", self._pick_language)

        body = tk.Frame(win, bg=t["panel"])
        body.pack(fill="both", expand=True, padx=px(10), pady=(px(10), 0))
        sb = tk.Scrollbar(body)
        sb.pack(side="right", fill="y")
        self.text = tk.Text(body, wrap="word", bg=t["input"], fg=t["fg"], insertbackground=t["fg"],
                            relief="flat", font=font(11), padx=px(8), pady=px(8), undo=True,
                            yscrollcommand=sb.set, selectbackground=t["accent_bg"], height=9, width=52)
        self.text.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.text.yview)

        foot = tk.Frame(win, bg=t["panel"])
        foot.pack(fill="x", padx=px(10), pady=px(10))
        self.status = tk.Label(foot, text="", bg=t["panel"], fg=t["dim"], font=font(9), anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        for label, cmd, primary in (("Đóng", self.close, False), ("Chép", self.copy_current, True)):
            b = tk.Label(foot, text=label, padx=px(16), pady=px(6), cursor="hand2", font=font(10, bold=primary),
                         bg=(t["accent_bg"] if primary else t["bg"]), fg="white" if primary else t["fg"])
            b.pack(side="right", padx=(px(6), 0))
            b.bind("<Button-1>", lambda e, c=cmd: c())

        self._place(near)
        self.show_tab(start_tab, initial=True)
        self.root.after(80, self._drain)

    # ------------------------------------------------------------ bố cục
    def _place(self, near) -> None:
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        bounds = virtual_screen(self.root)
        if near:
            x, y = near[0] - w, near[1] - h - int(10 * self.s)
        else:
            x, y = bounds[0] + (bounds[2] - w) // 2, bounds[1] + (bounds[3] - h) // 2
        x, y = clamp_pos(x, y, w, h, bounds, margin=int(8 * self.s))
        self.win.geometry(f"+{x}+{y}")

    def current_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def _store_current(self) -> None:
        if self.tab == "orig":
            self.orig = self.current_text()
        elif self.tab == "trans" and self.trans is not None:
            self.trans = self.current_text()

    def _set_text(self, s: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", s)
        self.text.edit_reset()

    def set_status(self, msg: str, err: bool = False) -> None:
        self.status.configure(text=msg, fg="#f87171" if err else THEME["dim"])

    # ------------------------------------------------------------ tab
    def show_tab(self, tab: str, initial: bool = False) -> None:
        if tab == self.tab:
            return
        self._store_current()
        self.tab = tab
        for k, b in self.tab_btns.items():
            b.configure(fg=THEME["accent"] if k == tab else THEME["dim"])
        if tab == "orig":
            self.lang_btn.pack_forget()
            self._set_text(self.orig)
            if not initial:
                self.copy_current(auto=True)
            else:
                self.set_status("Đã chép chữ — bấm Ctrl+V để dán. Chữ sửa được trước khi chép/dịch.")
        else:
            self.lang_btn.pack(side="right")
            self._update_lang_label()
            self._start_translation()

    # ------------------------------------------------------------ dịch
    def _update_lang_label(self) -> None:
        self.lang_btn.configure(text=f"→ {tr.lang_name(self.target)}  ▾")

    def _pick_language(self, event=None) -> None:
        items = [MenuItem(label=name, checked=(code == self.target), action=lambda c=code: self.set_target(c))
                 for code, name in tr.LANGS.items()]
        x = self.lang_btn.winfo_rootx()
        y = self.lang_btn.winfo_rooty() + self.lang_btn.winfo_height()
        self.menu.show(items, x, y)

    def set_target(self, code: str) -> None:
        self.target, self._explicit = code, True
        self.cfg.target_lang = code
        self.save_cfg()
        self._update_lang_label()
        self.trans_key = None
        if self.tab == "trans":
            self._start_translation()

    def _start_translation(self) -> None:
        src = self.orig.strip()
        if not src:
            self._set_text("")
            self.set_status("Chưa có chữ để dịch.")
            return
        key = (src, self.target)
        if self.trans_key == key and self.trans is not None:
            self._set_text(self.trans)
            self.copy_current(auto=True)
            return
        self._req += 1
        req = self._req
        self._set_text("")
        self.set_status("Đang dịch…")

        def work():
            try:
                self._q.put((req, key, self.translate_fn(src, self.target), None))
            except Exception as exc:  # noqa: BLE001
                self._q.put((req, key, None, exc))

        threading.Thread(target=work, name="translate", daemon=True).start()

    def _drain(self) -> None:
        if self._closed:
            return
        try:
            while True:
                req, key, result, exc = self._q.get_nowait()
                if req != self._req or self.tab != "trans":
                    continue                                    # kết quả cũ / đã rời tab
                if exc is not None:
                    msg = str(exc) if isinstance(exc, tr.TranslateError) else f"Lỗi dịch: {exc}"
                    self.set_status(msg, err=True)
                    continue
                self.trans, self.trans_key = result.text, key
                self._set_text(result.text)
                src = tr.lang_name(result.source) if result.source else "?"
                self.set_status(f"{src} → {tr.lang_name(self.target)}")
                self.copy_current(auto=True)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    # ------------------------------------------------------------ chép / đóng
    def copy_current(self, auto: bool = False) -> None:
        if auto and not self.cfg.translate_autocopy:
            return
        s = self.current_text()
        if not s.strip():
            return
        try:
            self.copy_fn(s)
        except Exception as exc:  # noqa: BLE001
            self.set_status(str(exc), err=True)
            return
        what = "chữ gốc" if self.tab == "orig" else "bản dịch"
        self.set_status(f"Đã chép {what} ({len(s)} ký tự) — Ctrl+V để dán")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.menu.close()
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.on_close:
            self.on_close(self)

    def focus(self) -> None:
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except Exception:
            pass
