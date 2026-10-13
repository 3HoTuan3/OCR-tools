"""Menu chuột phải kiểu hiện đại (nền tối, icon, dấu tick, menu con) vẽ bằng Tk.

Tk.Menu gốc trên Windows không chỉnh được giao diện nên menu được dựng từ các cửa sổ Toplevel không viền.
Đóng menu khi: bấm mục, Esc, bấm ra ngoài (Windows: dò trạng thái nút chuột), mất focus.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Optional, Union

from .uiutil import THEME, button_down, clamp_pos, font, now, scale, tk_icon, virtual_screen

Items = Union[list, Callable[[], list]]


@dataclass
class MenuItem:
    label: str = ""
    icon: str = ""
    action: Optional[Callable[[], None]] = None
    children: Optional[Items] = None
    checked: Optional[bool] = None      # None: không có ô tick; True: ✓; False: chừa chỗ trống
    enabled: bool = True
    separator: bool = False
    hint: str = ""                      # chữ mờ căn phải (vd. phím tắt)
    accent: bool = False                # tô màu nhấn (mục chính)


SEP = MenuItem(separator=True)


class _Level:
    def __init__(self, win, depth, rows):
        self.win, self.depth, self.rows = win, depth, rows   # rows: [(frame, widgets, item)]
        self.hovered = None


class PopupMenu:
    MIN_W = 236

    def __init__(self, root, theme=THEME):
        self.root, self.t = root, theme
        self.levels: list[_Level] = []
        self.closed_at = 0.0
        self._poll_id = None
        self._armed = False
        self._open_job = None
        self.s = scale(root)

    # ------------------------------------------------------------ công khai
    @property
    def is_open(self) -> bool:
        return bool(self.levels)

    def show(self, items: Items, x: int, y: int) -> None:
        self.close()
        items = items() if callable(items) else items
        self._armed = False
        self._add_level(items, 0, x, y, anchor=(x, y))
        self._poll()

    def close(self) -> None:
        had = bool(self.levels)
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        self._cancel_open()
        for lv in self.levels:
            try:
                lv.win.destroy()
            except Exception:
                pass
        self.levels = []
        if had:
            self.closed_at = now()

    # ------------------------------------------------------------ dựng cấp menu
    def _px(self, n: int) -> int:
        return max(1, int(n * self.s))

    def _add_level(self, items, depth, x, y, anchor=None, parent_row=None) -> None:
        t = self.t
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        outer = tk.Frame(win, bg=t["border"], padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=t["bg"], pady=self._px(6))
        inner.pack()
        tk.Frame(inner, width=self._px(self.MIN_W), height=0, bg=t["bg"]).pack()   # độ rộng tối thiểu
        rows = []
        level = _Level(win, depth, rows)
        for item in items:
            if item.separator:
                tk.Frame(inner, height=1, bg=t["sep"]).pack(fill="x", padx=self._px(12), pady=self._px(4))
                continue
            rows.append(self._make_row(inner, level, item))
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<FocusOut>", lambda e: self.root.after(150, self._check_focus))

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        bounds = virtual_screen(self.root)
        if parent_row is None:                       # menu gốc: ưu tiên mọc lên phía trên nếu thiếu chỗ phía dưới
            ax, ay = anchor
            px_, py_ = ax, ay
            if py_ + h > bounds[1] + bounds[3]:
                py_ = ay - h
            if px_ + w > bounds[0] + bounds[2]:
                px_ = ax - w
        else:
            pw = self.levels[-1].win
            px_ = pw.winfo_rootx() + pw.winfo_width() - 2
            py_ = parent_row.winfo_rooty() - self._px(7)
            if px_ + w > bounds[0] + bounds[2]:
                px_ = pw.winfo_rootx() - w + 2
        px_, py_ = clamp_pos(px_, py_, w, h, bounds, margin=2)
        win.geometry(f"+{px_}+{py_}")
        win.deiconify()
        win.lift()
        try:
            win.focus_force()
        except Exception:
            pass
        self.levels.append(level)

    def _make_row(self, parent, level, item: MenuItem):
        t = self.t
        fg = t["fg"] if item.enabled else t["dim"]
        row = tk.Frame(parent, bg=t["bg"])
        row.pack(fill="x", padx=self._px(5))
        ipad = self._px(7)
        widgets = [row]
        icolor = t["accent"] if item.accent and item.enabled else fg
        img = tk_icon(self.root, item.icon, self._px(18), icolor)
        if img is not None:
            icon = tk.Label(row, image=img, bg=t["bg"], width=self._px(26))
        else:
            icon = tk.Label(row, text=item.icon, width=3, bg=t["bg"], font=font(11, symbol=True), fg=icolor)
        icon.pack(side="left", pady=ipad, padx=(self._px(4), 0))
        text = tk.Label(row, text=item.label, anchor="w", bg=t["bg"], fg=fg, font=font(10, bold=item.accent))
        text.pack(side="left", fill="x", expand=True, padx=(self._px(4), self._px(10)))
        tail_txt = "›" if item.children is not None else ("✓" if item.checked else "")
        tail_img = None
        if not item.hint and tail_txt:
            tail_img = tk_icon(self.root, "chevron" if item.children is not None else "check", self._px(14),
                               t["dim"] if item.children is not None else (t["accent"] if item.enabled else fg))
        if tail_img is not None:
            tail = tk.Label(row, image=tail_img, bg=t["bg"], width=self._px(18))
        else:
            tail = tk.Label(row, text=item.hint or tail_txt, width=(0 if item.hint else 2), bg=t["bg"],
                            fg=(t["dim"] if item.hint else fg), font=font(10 if item.hint else 12, symbol=not item.hint))
        tail.pack(side="right", padx=(0, self._px(8)))
        widgets += [icon, text, tail]
        for w in widgets:
            w.bind("<Enter>", lambda e, r=row: self._hover(level, r))
            w.bind("<ButtonRelease-1>", lambda e, r=row: self._activate(level, r))
        return (row, widgets, item)

    # ------------------------------------------------------------ tương tác
    def _hover(self, level: _Level, row) -> None:
        t = self.t
        for fr, ws, item in level.rows:
            on = fr is row and item.enabled
            for w in ws:
                w.configure(bg=t["hover"] if on else t["bg"])
        level.hovered = row
        item = self._item_of(level, row)
        self._cancel_open()
        if item is not None and item.children is not None and item.enabled:
            self._open_job = self.root.after(170, lambda: self._open_child(level, row, item))
        else:
            self._close_after(level.depth)

    @staticmethod
    def _item_of(level, row):
        for fr, _ws, item in level.rows:
            if fr is row:
                return item
        return None

    def _cancel_open(self) -> None:
        if self._open_job is not None:
            try:
                self.root.after_cancel(self._open_job)
            except Exception:
                pass
            self._open_job = None

    def _close_after(self, depth: int) -> None:
        while len(self.levels) > depth + 1:
            lv = self.levels.pop()
            try:
                lv.win.destroy()
            except Exception:
                pass

    def _open_child(self, level: _Level, row, item: MenuItem) -> None:
        self._open_job = None
        if level not in self.levels:
            return
        self._close_after(level.depth)
        kids = item.children() if callable(item.children) else item.children
        if not kids:
            kids = [MenuItem(label="(trống)", enabled=False)]
        self._add_level(kids, level.depth + 1, 0, 0, parent_row=row)

    def _activate(self, level: _Level, row) -> None:
        item = self._item_of(level, row)
        if item is None or not item.enabled:
            return
        if item.children is not None:
            self._cancel_open()
            self._open_child(level, row, item)
            return
        action = item.action
        self.close()
        if action is not None:
            self.root.after(15, action)           # chạy sau khi menu đã đóng hẳn

    # ------------------------------------------------------------ đóng khi bấm ra ngoài / mất focus
    def _inside(self, x: int, y: int) -> bool:
        for lv in self.levels:
            try:
                wx, wy = lv.win.winfo_rootx(), lv.win.winfo_rooty()
                if wx <= x < wx + lv.win.winfo_width() and wy <= y < wy + lv.win.winfo_height():
                    return True
            except Exception:
                pass
        return False

    def _poll(self) -> None:
        if not self.levels:
            return
        try:
            px, py = self.root.winfo_pointerxy()
            if button_down():
                if self._armed and not self._inside(px, py):
                    self.close()
                    return
            else:
                self._armed = True                # lần mở bằng chuột phải: đợi nhả nút rồi mới theo dõi
        except Exception:
            pass
        self._poll_id = self.root.after(40, self._poll)

    def _check_focus(self) -> None:
        if not self.levels:
            return
        try:
            f = self.root.focus_get()
        except Exception:
            f = None
        if f is None or f.winfo_toplevel() not in [lv.win for lv in self.levels]:
            self.close()
