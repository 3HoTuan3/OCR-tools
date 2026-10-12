"""Bật/tắt tự khởi động cùng máy (Windows: registry HKCU\\...\\Run, Linux: ~/.config/autostart)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

NAME = "ocrtool"


def _python_exe() -> str:
    exe = sys.executable
    if sys.platform == "win32":
        w = Path(exe).with_name("pythonw.exe")   # không hiện cửa sổ console
        if w.exists():
            return str(w)
    return exe


def command() -> str:
    return f'"{_python_exe()}" -m ocrtool.tray'


# ------------------------------------------------------------------ Windows
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _win_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, NAME)
            return True
    except OSError:
        return False


def _win_set(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except OSError:
                pass


# ------------------------------------------------------------------ Linux
def _desktop_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / f"{NAME}.desktop"


def _linux_set(enabled: bool) -> None:
    path = _desktop_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=OCR Tray\n"
            f"Exec={command()}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
            encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------ công khai
def is_enabled() -> bool:
    return _win_is_enabled() if sys.platform == "win32" else _desktop_file().exists()


def set_enabled(enabled: bool) -> None:
    if sys.platform == "win32":
        _win_set(enabled)
    else:
        _linux_set(enabled)
