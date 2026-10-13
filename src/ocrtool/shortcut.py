"""Tạo lối tắt "OCR Tool" (có logo) ở Start Menu và Desktop trên Windows, để mở app bằng cách gõ "OCR" vào Start.

    python -m ocrtool.shortcut          (setup.bat tự chạy lệnh này)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .icons import asset

NAME = "OCR Tool"


def _pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def create(desktop: bool = True, start_menu: bool = True) -> list[str]:
    if sys.platform != "win32":
        raise RuntimeError("Chỉ hỗ trợ Windows")
    root = Path(__file__).resolve().parents[2]
    targets = []        # (tên hiển thị, biểu thức PowerShell cho thư mục)
    if start_menu:
        targets.append(("Start Menu", "[Environment]::GetFolderPath('Programs')"))
    if desktop:      # GetFolderPath đúng cả khi Desktop nằm trong OneDrive
        targets.append(("Desktop", "[Environment]::GetFolderPath('Desktop')"))
    made = []
    for label, folder in targets:
        script = (
            "$p = Join-Path (" + folder + ") " + _ps_quote(f"{NAME}.lnk") + ";"
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($p);"
            "$s.TargetPath = " + _ps_quote(_pythonw()) + ";"
            "$s.Arguments = '-m ocrtool.tray';"
            "$s.WorkingDirectory = " + _ps_quote(str(root)) + ";"
            "$s.IconLocation = " + _ps_quote(str(asset("app.ico"))) + ";"
            "$s.Description = 'Chụp vùng màn hình -> chữ, dịch, lăng kính dịch';"
            "$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       check=True, capture_output=True, creationflags=0x08000000)
        made.append(label)
    return made


def remove() -> None:
    script = ";".join(
        f"Remove-Item -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('{f}')) "
        f"{_ps_quote(NAME + '.lnk')})" for f in ("Programs", "Desktop"))
    subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, creationflags=0x08000000)


if __name__ == "__main__":
    try:
        print("Đã tạo lối tắt:", ", ".join(create()))
    except Exception as exc:  # noqa: BLE001
        print("Không tạo được lối tắt:", exc)
        sys.exit(1)
