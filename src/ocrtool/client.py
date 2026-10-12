"""Phía app nền của tiến trình OCR thường trực (`ocrtool.worker`).

* Lần đầu cần OCR (hoặc khi bắt đầu kéo chọn vùng) mới khởi động tiến trình; engine nạp song song lúc bạn kéo chuột.
* Các lần sau dùng lại engine đã nạp nên chỉ còn thời gian nhận dạng.
* Không dùng quá `idle_s` giây thì tiến trình tự thoát để trả RAM (idle_s < 0: giữ mãi; 0: thoát ngay sau mỗi lần).
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger("ocrtool")
REQUEST_TIMEOUT_S = 120


def _python_exe() -> str:
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")          # stdin/stdout chắc chắn hoạt động
        if console.exists():
            return str(console)
    return str(exe)


class OcrClient:
    def __init__(self, lang_fn=lambda: "vie+eng", idle_s: float = 900, command=None):
        self.lang_fn = lang_fn
        self.idle_s = idle_s
        self.command = command or (lambda: [_python_exe(), "-m", "ocrtool.worker"])
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._pending: dict[int, tuple] = {}      # id -> (callback, deadline, path)
        self._ids = itertools.count(1)
        self._last_used = time.monotonic()
        self._tmp = Path(tempfile.mkdtemp(prefix="ocrtool_client_"))
        self._stop = threading.Event()
        threading.Thread(target=self._watchdog, name="ocr-watchdog", daemon=True).start()

    # ------------------------------------------------------------ trạng thái
    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._pending)

    # ------------------------------------------------------------ tiến trình
    def _ensure(self) -> subprocess.Popen:
        with self._lock:
            if self.running:
                return self._proc
            flags = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            src = str(Path(__file__).resolve().parents[1])            # chạy được cả khi chưa pip install -e
            env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            err = open(self._tmp / "worker_stderr.txt", "ab")
            proc = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=err, env=env, creationflags=flags)
            err.close()
            self._proc = proc
            threading.Thread(target=self._reader, args=(proc,), name="ocr-reader", daemon=True).start()
            log.info("Đã khởi động tiến trình OCR (pid %s)", proc.pid)
            return proc

    def _send(self, msg: dict) -> None:
        proc = self._ensure()
        proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def _reader(self, proc: subprocess.Popen) -> None:
        for raw in proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            self._finish(msg.get("id"), msg)
        # tiến trình đã thoát: báo lỗi cho các yêu cầu còn chờ
        with self._lock:
            if self._proc is proc:
                self._proc = None
            dead = [rid for rid, _ in self._pending.items()]
        tail = ""
        try:
            tail = (self._tmp / "worker_stderr.txt").read_text(encoding="utf-8", errors="replace")[-600:]
        except Exception:
            pass
        for rid in dead:
            self._finish(rid, {"ok": False, "error": "Tiến trình OCR dừng đột ngột.\n" + tail})

    def _finish(self, rid, msg: dict) -> None:
        with self._lock:
            entry = self._pending.pop(rid, None)
            self._last_used = time.monotonic()
        if entry is None:
            return
        cb, _deadline, path = entry
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
        if cb is not None:
            try:
                cb(msg)
            except Exception:
                log.exception("Lỗi khi xử lý kết quả OCR")
        if self.idle_s == 0 and not self.busy:
            self.shutdown()

    def _request(self, msg: dict, cb, path=None) -> int:
        rid = next(self._ids)
        msg["id"] = rid
        msg.setdefault("lang", self.lang_fn())
        with self._lock:
            self._pending[rid] = (cb, time.monotonic() + REQUEST_TIMEOUT_S, path)
            self._last_used = time.monotonic()
        try:
            self._send(msg)
        except Exception as exc:
            self._finish(rid, {"ok": False, "error": f"Không gửi được yêu cầu tới tiến trình OCR: {exc}"})
        return rid

    # ------------------------------------------------------------ công khai
    def warm(self) -> None:
        """Bắt đầu nạp engine nếu chưa nạp (không chờ)."""
        if not self.running:
            self._request({"op": "warm"}, None)

    def ocr(self, image, callback, **opts) -> int:
        """OCR ảnh PIL ở tiến trình nền; callback(msg) được gọi ở luồng nền khi xong."""
        path = self._tmp / f"req_{time.monotonic_ns()}.png"
        image.save(path, compress_level=1)
        return self._request({"op": "ocr", "path": str(path), **opts}, callback, str(path))

    def shutdown(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write(b'{"op": "quit"}\n')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        log.info("Đã tắt tiến trình OCR để trả RAM")

    def close(self) -> None:
        self._stop.set()
        self.shutdown()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _watchdog(self) -> None:
        while not self._stop.wait(2.0):
            now = time.monotonic()
            with self._lock:
                late = [rid for rid, (_cb, dl, _p) in self._pending.items() if now > dl]
                idle = (not self._pending and self.idle_s > 0 and now - self._last_used > self.idle_s)
            for rid in late:
                self._finish(rid, {"ok": False, "error": "Quá thời gian chờ OCR."})
                proc = self._proc
                if proc is not None:
                    proc.kill()
            if idle and self.running:
                self.shutdown()
