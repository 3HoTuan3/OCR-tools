"""App nền: cửa sổ nổi nhỏ (bấm trái = chụp, bấm phải = menu) + biểu tượng khay hệ thống.

Chạy:  python -m ocrtool.tray      (Windows: ocr-tray.bat để không hiện console)

Chụp xong chữ vào clipboard ngay (Ctrl+V / Win+V); cửa sổ kết quả cho phép sửa chữ hoặc chuyển sang tab Dịch.
Tiến trình này rất nhẹ: mỗi lần chụp chạy `ocrtool.job` trong một tiến trình riêng rồi thoát (trả hết RAM engine).
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
from .icons import make_icon_image
from .uiutil import now

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

    @property
    def busy(self) -> bool:
        return self._busy.locked()

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


class App:
    """Điều phối: cửa sổ nổi (Tk, luồng chính) + khay (pystray, luồng nền) + tiến trình chụp."""

    def __init__(self, root, cfg: Config, command=None):
        import queue
        from .menu import PopupMenu
        from .widget import FloatingButton

        self.root, self.cfg = root, cfg
        self.tray_ok = False
        self.icon = None
        self.result_win = None
        self.hotkey = None
        self._bus: queue.Queue = queue.Queue()
        self.launcher = JobLauncher(lambda r: self.post(lambda: self.handle_result(r)), command=command)
        self.menu = PopupMenu(root)
        self.widget = FloatingButton(root, cfg, on_click=self._on_click, on_menu=self.show_menu,
                                     on_moved=self._on_moved)
        if not cfg.float_visible:
            self.widget.hide()
        self.root.after(60, self._pump)
        self._start_hotkey()

    # ------------------------------------------------------------ luồng
    def post(self, fn) -> None:
        """Gọi `fn` ở luồng Tk (an toàn khi gọi từ luồng khác)."""
        self._bus.put(fn)

    def _pump(self) -> None:
        import queue
        try:
            while True:
                fn = self._bus.get_nowait()
                try:
                    fn()
                except Exception:
                    log.exception("Lỗi trong tác vụ giao diện")
        except queue.Empty:
            pass
        self.root.after(60, self._pump)

    # ------------------------------------------------------------ cấu hình
    def save(self) -> None:
        self.cfg.save()

    def set_option(self, name: str, value) -> None:
        setattr(self.cfg, name, value)
        self.save()
        if name == "float_size":
            self.widget.apply_size()
            self.widget.place(*self.widget.position())
        elif name == "float_opacity":
            self.widget.apply_opacity()
        elif name == "float_topmost":
            self.widget.apply_topmost()

    def toggle(self, name: str) -> None:
        self.set_option(name, not getattr(self.cfg, name))

    def set_output_mode(self, mode: str) -> None:
        self.cfg.table_mode = mode == "table"
        self.cfg.join_lines = mode == "single"
        self.save()

    def autostart_enabled(self) -> bool:
        try:
            return autostart.is_enabled()
        except Exception:
            return False

    def toggle_autostart(self) -> None:
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except Exception:
            log.exception("Không đổi được tự khởi động")
            self.toast("Không đổi được tự khởi động (xem file log)")

    # ------------------------------------------------------------ cửa sổ nổi
    def _on_click(self) -> None:
        if now() - self.menu.closed_at < 0.3:        # cú bấm vừa dùng để đóng menu
            return
        self.capture()

    def _on_moved(self, x: int, y: int) -> None:
        self.cfg.float_x, self.cfg.float_y = x, y
        self.save()

    def show_menu(self, x: int, y: int) -> None:
        from .appmenu import build_menu

        self.menu.show(lambda: build_menu(self), x, y)

    def reset_position(self) -> None:
        self.widget.place(-1, -1)
        self._on_moved(*self.widget.position())

    def show_widget(self) -> None:
        self.cfg.float_visible = True
        self.save()
        self.widget.show()

    def hide_widget(self) -> None:
        if not self.tray_ok:
            self.toast("Không có biểu tượng khay để mở lại nên không ẩn được cửa sổ nổi")
            return
        self.cfg.float_visible = False
        self.save()
        self.widget.hide()

    def _near(self):
        try:
            x, y = self.widget.position()
            return x + self.widget.size, y
        except Exception:
            return None

    def toast(self, msg: str) -> None:
        from .widget import show_toast
        try:
            show_toast(self.root, msg, near=self._near() if self.widget.visible else None)
        except Exception:
            log.exception("Không hiện được thông báo")

    # ------------------------------------------------------------ chụp
    def capture(self) -> None:
        if self.launcher.busy:
            log.info("Đang có một lần chụp, bỏ qua lần bấm này")
            return
        self.menu.close()
        self.widget.set_state("busy")
        if self.widget.visible:
            self.widget.hide()                     # để cửa sổ nổi không lọt vào ảnh chụp
            self.root.update_idletasks()
        if not self.launcher.start():
            self._restore()

    def _restore(self) -> None:
        self.widget.set_state("idle")
        if self.cfg.float_visible:
            self.widget.show()

    def handle_result(self, result: dict) -> None:
        self._restore()
        status = result.get("status")
        log.info("Kết quả: %s", {k: v for k, v in result.items() if k not in ("message", "text")})
        if status == "error":
            log.error("Chi tiết lỗi:\n%s", result.get("message", ""))
        for w in result.get("warnings", []):
            log.warning(w)
        cfg = Config.load()                    # thấy ngay thay đổi cấu hình sửa bằng tay
        self.cfg.min_score, self.cfg.lang = cfg.min_score, cfg.lang
        if status == "ok" and self.cfg.after_capture in ("window", "translate") and result.get("text"):
            self.open_result(result["text"], "trans" if self.cfg.after_capture == "translate" else "orig")
            if result.get("warnings") and self.cfg.notify:
                self.toast("OCR: thiếu Tesseract/dữ liệu tiếng Việt — " + result["warnings"][0][:160])
            return
        info = describe(result)
        if info and (self.cfg.notify or status in ("error", "empty")):
            self.toast(info[0] + (("\n" + info[1]) if info[1] else ""))
        if status == "ok" and result.get("warnings") and self.cfg.notify:
            self.toast("OCR: thiếu Tesseract/dữ liệu tiếng Việt\n" + result["warnings"][0][:160])

    def open_result(self, text: str, tab: str = "orig") -> None:
        from . import translate as tr
        from .clipboard import set_text
        from .result import ResultWindow

        if self.result_win is not None:
            self.result_win.close()
        self.result_win = ResultWindow(
            self.root, text, self.cfg,
            translate_fn=lambda t, tgt: tr.translate(t, tgt, engine=self.cfg.translate_engine),
            copy_fn=set_text, save_cfg=self.save, start_tab=tab, near=self._near(),
            on_close=lambda w: setattr(self, "result_win", None) if self.result_win is w else None)
        self.result_win.focus()

    # ------------------------------------------------------------ lịch sử
    def history_items(self, limit: int = 8) -> list[tuple[str, Path]]:
        out = []
        try:
            files = sorted(history_dir().glob("*.txt"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
            for p in files[:limit]:
                text = " ".join(p.read_text(encoding="utf-8", errors="replace").split())
                out.append(((text[:40] + ("…" if len(text) > 40 else "")) or "(trống)", p))
        except Exception:
            log.exception("Không đọc được lịch sử")
        return out

    def copy_history(self, path: Path) -> None:
        from .clipboard import set_text
        try:
            text = Path(path).read_text(encoding="utf-8")
            set_text(text)
        except Exception as exc:
            self.toast(f"Không chép được: {exc}")
            return
        if self.cfg.after_capture != "copy":
            self.open_result(text, "orig")
        else:
            self.toast(f"Đã chép lại {len(text)} ký tự — Ctrl+V để dán")

    def open_history(self) -> None:
        _open_path(history_dir())

    def open_log(self) -> None:
        _open_path(log_path())

    # ------------------------------------------------------------ phím tắt toàn cục
    def _start_hotkey(self) -> None:
        from .hotkey import GlobalHotkey

        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
        if self.cfg.hotkey:
            hk = GlobalHotkey(self.cfg.hotkey, lambda: self.post(self.capture),
                              on_error=lambda m: self.post(lambda: self.toast(m)))
            self.hotkey = hk if hk.start() else None

    def toggle_hotkey(self) -> None:
        from .appmenu import DEFAULT_HOTKEY
        self.cfg.hotkey = "" if self.cfg.hotkey else DEFAULT_HOTKEY
        self.save()
        self._start_hotkey()

    # ------------------------------------------------------------ khay hệ thống
    def start_tray(self) -> None:
        try:
            import pystray

            Item = pystray.MenuItem
            menu = pystray.Menu(
                Item("Chụp vùng để OCR", lambda i, it: self.post(self.capture), default=True),
                Item("Hiện cửa sổ nổi", lambda i, it: self.post(self.show_widget),
                     checked=lambda it: self.cfg.float_visible),
                Item("Khởi động cùng máy", lambda i, it: self.post(self.toggle_autostart),
                     checked=lambda it: self.autostart_enabled()),
                Item("Mở file log", lambda i, it: self.post(self.open_log)),
                Item("Thoát", lambda i, it: self.post(self.quit)),
            )
            self.icon = pystray.Icon("ocrtool", make_icon_image(), "OCR - click to capture", menu)

            def setup(icon):
                icon.visible = True
                self.tray_ok = True

            self.icon.run_detached(setup)
        except Exception:
            log.exception("Không khởi động được biểu tượng khay (cửa sổ nổi vẫn dùng được)")
            self.icon = None

    def show_from_other_instance(self) -> None:
        self.post(self.show_widget)

    def quit(self) -> None:
        try:
            if self.hotkey:
                self.hotkey.stop()
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass
        self.root.quit()


def _serve_lock(sock, on_show) -> None:
    """Bản chạy thứ hai gửi 'show' vào cổng khoá để bản đầu hiện lại cửa sổ nổi."""
    while True:
        try:
            conn, _ = sock.accept()
        except OSError:
            return
        try:
            conn.settimeout(1)
            if conn.recv(16).startswith(b"show"):
                on_show()
        except Exception:
            pass
        finally:
            conn.close()


def _ping_existing() -> None:
    try:
        with socket.create_connection(("127.0.0.1", _LOCK_PORT), timeout=1) as s:
            s.sendall(b"show")
    except OSError:
        pass


def main() -> int:
    _setup_logging()
    lock = _single_instance()
    if lock is None:
        log.info("Đã có một bản đang chạy; yêu cầu nó hiện cửa sổ nổi rồi thoát.")
        _ping_existing()
        return 0

    try:
        import tkinter as tk
        from .snip import set_dpi_aware

        set_dpi_aware()
        root = tk.Tk()
    except Exception:
        log.exception("Không khởi tạo được giao diện Tk (thiếu tkinter hoặc không có màn hình)")
        return 1

    cfg = Config.load()
    cfg.save()
    app = App(root, cfg)
    threading.Thread(target=_serve_lock, args=(lock, app.show_from_other_instance),
                     name="lock-server", daemon=True).start()
    app.start_tray()
    log.info("OCR đã chạy (cửa sổ nổi + khay)")
    try:
        root.mainloop()
    finally:
        lock.close()
        try:
            root.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
