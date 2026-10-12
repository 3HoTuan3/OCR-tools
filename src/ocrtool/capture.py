"""Lấy ảnh đầu vào cho dòng lệnh: chọn vùng màn hình, hoặc ảnh trong clipboard."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image


class CaptureError(RuntimeError):
    pass


def grab_clipboard_image() -> Image.Image:
    """Ảnh đang nằm trong clipboard (vd. sau khi bấm Win+Shift+S trên Windows)."""
    from PIL import ImageGrab

    try:
        data = ImageGrab.grabclipboard()
    except Exception as exc:  # Linux thiếu xclip / wl-paste
        raise CaptureError(f"Không đọc được clipboard: {exc}") from exc
    if isinstance(data, Image.Image):
        return data
    if isinstance(data, list) and data:  # file được copy trong Explorer
        try:
            return Image.open(data[0])
        except Exception as exc:
            raise CaptureError(f"Clipboard chứa file không phải ảnh: {data[0]}") from exc
    raise CaptureError("Clipboard không có ảnh. Hãy chụp màn hình (Win+Shift+S) rồi chạy lại.")


def show_toast(message: str, ms: int = 1600) -> None:
    """Hiện thông báo nhỏ góc dưới phải màn hình (dùng khi chạy không có khay/console)."""
    try:
        import tkinter as tk

        from .snip import set_dpi_aware

        set_dpi_aware()
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        tk.Label(root, text=message, bg="#1f2937", fg="white", padx=18, pady=10,
                 font=("Segoe UI", 11)).pack()
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        root.geometry(f"+{root.winfo_screenwidth() - w - 24}+{root.winfo_screenheight() - h - 72}")
        root.after(ms, root.destroy)
        root.mainloop()
    except Exception:
        pass


def _grab_wayland() -> Image.Image | None:
    """Wayland không cho chụp màn hình trực tiếp: nhờ công cụ của desktop chọn vùng."""
    tmp = os.path.join(tempfile.mkdtemp(prefix="ocrtool_"), "shot.png")
    attempts = []
    if shutil.which("grim") and shutil.which("slurp"):
        region = subprocess.run(["slurp"], capture_output=True, text=True).stdout.strip()
        if region:
            attempts.append(["grim", "-g", region, tmp])
    if shutil.which("gnome-screenshot"):
        attempts.append(["gnome-screenshot", "-a", "-f", tmp])
    if shutil.which("spectacle"):
        attempts.append(["spectacle", "-b", "-r", "-n", "-o", tmp])
    for cmd in attempts:
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            return Image.open(tmp).copy()
    raise CaptureError(
        "Wayland: cần một trong grim+slurp, gnome-screenshot hoặc spectacle để chọn vùng màn hình.")


def grab_screen_region(delay_s: float = 0.0) -> Image.Image | None:
    """Kéo chọn một vùng màn hình; trả về ảnh vùng đó (None nếu huỷ)."""
    if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return _grab_wayland()
    from .snip import SnipError, snip_screen

    try:
        return snip_screen(delay_s)
    except SnipError as exc:
        raise CaptureError(str(exc)) from exc
