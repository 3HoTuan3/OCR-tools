"""App khay hệ thống: bấm biểu tượng -> kéo chọn vùng -> chữ vào clipboard (Ctrl+V / Win+V).

Chạy:  python -m ocrtool.tray      (Windows: ocr-tray.bat để không hiện console)

Khay chỉ là app rất nhỏ. Mỗi lần chụp chạy `ocrtool.job` trong một tiến trình riêng rồi thoát.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import autostart
from .config import Config, history_dir, log_path

log = logging.getLogger("ocrtool")
_LOCK_PORT = 47831
JOB_TIMEOUT_S = 180


def _setup_logging() -> None:
    handler = RotatingFileHandler(log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(handler)

    sys.excepthook = lambda t, v, tb: log.error("Lỗi không bắt được", exc_info=(t, v, tb))
    threading.excepthook = lambda a: log.error(
        "Lỗi trong luồng %s", a.thread, exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def _single_instance():
    """Giữ một cổng localhost làm khoá; trả về socket (phải giữ tham chiếu) hoặc None nếu đã chạy."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def make_icon_image():
    """Biểu tượng 64x64: khung chụp màn hình có góc + vài dòng chữ."""
    from PIL import Image, ImageDraw

    size, c = 64, (37, 99, 235, 255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=12, fill=(255, 255, 255, 255),
                        outline=c, width=4)
    for i, w in enumerate((38, 30, 36)):
        y = 17 + i * 12
        d.rounded_rectangle((13, y, 13 + w, y + 6), radius=3, fill=c)
    return img


def _open_path(path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("Không mở được %s", path)


class JobLauncher:
    """Khởi động `ocrtool.job` trong tiến trình riêng; mỗi lúc chỉ một lần chụp."""

    def __init__(self, on_result, command=None, timeout=JOB_TIMEOUT_S):
        self.on_result = on_result
        self.command = command or (lambda: [sys.executable, "-m", "ocrtool.job"])
        self.timeout = timeout
        self._busy = threading.Lock()

    def start(self) -> bool:
        if not self._busy.acquire(blocking=False):
            return False                       # đang có một lần chụp
        threading.Thread(target=self._run, name="ocr-job", daemon=True).start()
        return True

    def _run(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="ocrtool_job_"))
        result_file, err_file = tmp / "result.json", tmp / "stderr.txt"
        result: dict
        try:
            flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
            with open(err_file, "wb") as err:
                proc = subprocess.Popen(self.command() + ["--result", str(result_file)],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=err, creationflags=flags)
                try:
                    proc.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    result = {"status": "error", "message": "Quá thời gian chờ, đã dừng tiến trình chụp."}
                else:
                    result = None
            if result is None:
                try:
                    result = json.loads(result_file.read_text(encoding="utf-8"))
                except Exception:
                    tail = err_file.read_text(encoding="utf-8", errors="replace")[-800:]
                    result = {"status": "error",
                              "message": f"Tiến trình chụp thoát (mã {proc.returncode}) mà không báo kết quả.\n{tail}"}
        except Exception as exc:
            log.exception("Không khởi động được tiến trình chụp")
            result = {"status": "error", "message": f"Không khởi động được tiến trình chụp: {exc}"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self._busy.release()
        try:
            self.on_result(result)
        except Exception:
            log.exception("Lỗi khi xử lý kết quả")


def describe(result: dict) -> tuple[str, str] | None:
    """(tiêu đề, nội dung) của thông báo cho người dùng; None nếu không cần báo (huỷ)."""
    status = result.get("status")
    if status == "ok":
        return (f"Đã chép {result.get('chars', 0)} ký tự — Ctrl+V để dán", result.get("snippet", ""))
    if status == "empty":
        return ("OCR", "Không nhận ra chữ nào trong vùng đã chọn. Clipboard giữ nguyên.")
    if status == "error":
        lines = str(result.get("message", "")).strip().splitlines()
        return ("OCR lỗi", (lines[-1] if lines else "Xem file log.")[:200])
    return None


def main() -> int:
    _setup_logging()
    lock = _single_instance()
    if lock is None:
        log.info("Đã có một bản đang chạy; thoát.")
        return 0

    import pystray

    cfg = Config.load()
    cfg.save()
    icon_holder: dict = {}

    def notify(title: str, msg: str) -> None:
        icon = icon_holder.get("icon")
        try:
            if icon is None:
                raise NotImplementedError
            icon.notify(msg, title)
        except NotImplementedError:      # backend X11 của pystray không có thông báo
            if shutil.which("notify-send"):
                subprocess.Popen(["notify-send", "-a", "ocrtool", title, msg])

    def on_result(result: dict) -> None:
        status = result.get("status")
        log.info("Kết quả: %s", {k: v for k, v in result.items() if k != "message"})
        if status == "error":
            log.error("Chi tiết lỗi:\n%s", result.get("message", ""))
        for w in result.get("warnings", []):
            log.warning(w)
        cfg_now = Config.load()               # thấy ngay thay đổi cấu hình bằng tay
        info = describe(result)
        if info and cfg_now.notify:
            notify(*info)
        if status == "ok" and result.get("warnings") and cfg_now.notify:
            notify("OCR: thiếu Tesseract/dữ liệu tiếng Việt", result["warnings"][0][:200])

    launcher = JobLauncher(on_result)

    def capture(icon=None, item=None):
        if not launcher.start():
            log.info("Đang có một lần chụp, bỏ qua lần bấm này")

    def toggle(attr: str):
        def action(icon, item):
            setattr(cfg, attr, not getattr(cfg, attr))
            cfg.save()
            icon.update_menu()
        return action

    def toggle_autostart(icon, item):
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except Exception:
            log.exception("Không đổi được tự khởi động")
        icon.update_menu()

    def quit_app(icon, item):
        icon.stop()

    Item = pystray.MenuItem
    menu = pystray.Menu(
        Item("Chụp vùng để OCR", capture, default=True),     # bấm trái vào biểu tượng
        pystray.Menu.SEPARATOR,
        Item("Hiện thông báo khi xong", toggle("notify"), checked=lambda i: cfg.notify),
        Item("Gộp các dòng thành một đoạn", toggle("join_lines"), checked=lambda i: cfg.join_lines),
        Item("Lưu lịch sử ảnh + chữ", toggle("keep_history"), checked=lambda i: cfg.keep_history),
        Item("Mở thư mục lịch sử", lambda i, it: _open_path(history_dir())),
        pystray.Menu.SEPARATOR,
        Item("Khởi động cùng máy", toggle_autostart, checked=lambda i: autostart.is_enabled()),
        Item("Mở file log", lambda i, it: _open_path(log_path())),
        Item("Thoát", quit_app),
    )
    icon = pystray.Icon("ocrtool", make_icon_image(), "OCR - click to capture", menu)
    icon_holder["icon"] = icon
    log.info("OCR tray đã chạy")
    icon.run()
    lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
