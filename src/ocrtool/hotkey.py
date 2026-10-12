"""Phím tắt toàn cục (Windows, RegisterHotKey; không cần thư viện ngoài). Nơi khác: không làm gì."""
from __future__ import annotations

import sys
import threading

_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8, "super": 0x8}
MOD_NOREPEAT = 0x4000


def parse_hotkey(spec: str):
    """'ctrl+alt+o' -> (modifiers, virtual-key). Ném ValueError nếu không hợp lệ."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("Phím tắt cần ít nhất một phím bổ trợ (ctrl/alt/shift/win) và một phím")
    mods, key = 0, parts[-1]
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"Phím bổ trợ không hợp lệ: {p}")
        mods |= _MODS[p]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"Phím không hợp lệ: {key}")
    return mods, vk


class GlobalHotkey:
    def __init__(self, spec: str, callback, on_error=None):
        self.spec, self.callback, self.on_error = spec, callback, on_error
        self._tid = None
        self._thread = None

    def start(self) -> bool:
        if sys.platform != "win32" or not self.spec:
            return False
        try:
            mods, vk = parse_hotkey(self.spec)
        except ValueError as exc:
            if self.on_error:
                self.on_error(str(exc))
            return False
        ready = threading.Event()
        state = {"ok": False}

        def loop():
            import ctypes
            from ctypes import wintypes

            u = ctypes.windll.user32
            self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
            state["ok"] = bool(u.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk))
            ready.set()
            if not state["ok"]:
                return
            msg = wintypes.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:            # WM_HOTKEY
                    try:
                        self.callback()
                    except Exception:
                        pass
            u.UnregisterHotKey(None, 1)

        self._thread = threading.Thread(target=loop, name="hotkey", daemon=True)
        self._thread.start()
        ready.wait(2)
        if not state["ok"] and self.on_error:
            self.on_error(f"Phím tắt {self.spec} đã bị chương trình khác dùng hoặc không hợp lệ")
        return state["ok"]

    def stop(self) -> None:
        if sys.platform == "win32" and self._tid:
            try:
                import ctypes

                ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)   # WM_QUIT
            except Exception:
                pass
        self._tid = None
