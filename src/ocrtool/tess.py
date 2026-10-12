"""Bộ bọc gọn quanh chương trình `tesseract` (gọi qua subprocess, không cần pytesseract).

Một lần gọi xử lý nhiều ảnh dòng (list-file) nên model chỉ nạp một lần."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


MIN_LINES_PER_PROC = 3     # ít dòng quá thì một tiến trình là đủ (nạp model cũng tốn ~0.1 s)


def default_workers() -> int:
    return max(1, min(6, os.cpu_count() or 2))


class TesseractUnavailable(RuntimeError):
    pass


_WIN_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def project_tessdata() -> str | None:
    """Thư mục tessdata/ nằm cạnh dự án (do scripts/get_tessdata.py tạo)."""
    env = os.environ.get("OCR_TESSDATA")
    if env and Path(env).is_dir():
        return env
    root = Path(__file__).resolve().parents[2]
    cand = root / "tessdata"
    return str(cand) if cand.is_dir() and any(cand.glob("*.traineddata")) else None


def find_executable() -> str | None:
    env = os.environ.get("OCR_TESSERACT")
    if env and Path(env).exists():
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        cands = list(_WIN_CANDIDATES)
        if local:
            cands.append(str(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe"))
        for c in cands:
            if Path(c).exists():
                return c
    return None


class TesseractBackend:
    def __init__(self, exe: str, lang: str = "vie+eng", tessdata: str | None = None,
                 timeout: float = 180.0, workers: int | None = None):
        self.exe = exe
        self.workers = workers or default_workers()
        self.lang = lang
        self.tessdata = tessdata
        self.timeout = timeout

    # ---------------------------------------------------------------- factory
    @classmethod
    def create(cls, lang: str = "vie+eng", tessdata: str | None = None) -> "TesseractBackend":
        exe = find_executable()
        if not exe:
            raise TesseractUnavailable(
                "Không tìm thấy Tesseract. Windows: winget install -e --id UB-Mannheim.TesseractOCR | "
                "Linux: sudo apt install tesseract-ocr")
        backend = cls(exe, lang=lang, tessdata=tessdata or project_tessdata())
        have = backend.available_langs()
        missing = [l for l in lang.split("+") if l not in have]
        if missing:
            raise TesseractUnavailable(
                f"Tesseract thiếu dữ liệu ngôn ngữ: {', '.join(missing)}. "
                f"Chạy: python scripts/get_tessdata.py")
        return backend

    # ------------------------------------------------------------------- misc
    def _env(self) -> dict:
        env = dict(os.environ)
        if self.tessdata:
            env["TESSDATA_PREFIX"] = self.tessdata
        env["OMP_THREAD_LIMIT"] = "1"  # nhanh hơn khi xử lý nhiều dòng ngắn
        return env

    @staticmethod
    def _popen_kwargs() -> dict:
        if sys.platform == "win32":
            return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
        return {}

    def version(self) -> str:
        try:
            out = subprocess.run([self.exe, "--version"], capture_output=True, text=True,
                                 timeout=30, env=self._env(), **self._popen_kwargs())
            return (out.stdout or out.stderr).splitlines()[0].strip()
        except Exception:
            return "?"

    def available_langs(self) -> set[str]:
        cmd = [self.exe, "--list-langs"]  # TESSDATA_PREFIX được đặt trong _env()
        out = subprocess.run(cmd, capture_output=True, timeout=30, env=self._env(),
                             **self._popen_kwargs())
        text = (out.stdout + out.stderr).decode("utf-8", "replace")
        langs = set()
        for line in text.splitlines()[1:]:
            line = line.strip()
            if line and not line.startswith("Error") and " " not in line:
                langs.add(line)
        return langs

    # ------------------------------------------------------------------- core
    def recognize_batch(self, images: list[np.ndarray]) -> list[tuple[str, float]]:
        """Nhận dạng nhiều ảnh một dòng chữ. Trả về [(text, conf 0-100), ...] đúng thứ tự.

        Chia thành vài nhóm chạy song song (mỗi tiến trình Tesseract một nhân CPU) cho nhanh hơn.
        """
        if not images:
            return []
        n = len(images)
        k = max(1, min(self.workers, (n + MIN_LINES_PER_PROC - 1) // MIN_LINES_PER_PROC))
        bounds = [(i * n // k, (i + 1) * n // k) for i in range(k)]
        with tempfile.TemporaryDirectory(prefix="ocrtool_") as tmp:
            procs = []
            for ci, (a, b) in enumerate(bounds):
                paths = []
                for i in range(a, b):
                    p = os.path.join(tmp, f"line_{i:04d}.png")
                    Image.fromarray(images[i]).save(p, compress_level=1)
                    paths.append(p)
                list_file = os.path.join(tmp, f"list_{ci}.txt")
                with open(list_file, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(paths))
                cmd = [self.exe, list_file, "stdout", "-l", self.lang, "--psm", "7",
                       "-c", "tessedit_create_tsv=1", "-c", "tessedit_create_txt=0"]
                procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              stdin=subprocess.DEVNULL, env=self._env(),
                                              **self._popen_kwargs()))
            out: list[tuple[str, float]] = []
            try:
                for proc, (a, b) in zip(procs, bounds):
                    stdout, stderr = proc.communicate(timeout=self.timeout)
                    if proc.returncode != 0 and not stdout:
                        raise TesseractUnavailable(
                            "Tesseract lỗi: " + stderr.decode("utf-8", "replace")[:300])
                    out.extend(self._parse_tsv(stdout.decode("utf-8", "replace"), b - a))
            finally:
                for proc in procs:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
        return out

    @staticmethod
    def _parse_tsv(tsv: str, n: int) -> list[tuple[str, float]]:
        words: dict[int, list[tuple[str, float]]] = {}
        for row in tsv.splitlines()[1:]:
            cols = row.split("\t")
            if len(cols) < 12 or cols[0] != "5":
                continue
            try:
                page = int(cols[1])
                conf = float(cols[10])
            except ValueError:
                continue
            text = cols[11].strip()
            if text and conf >= 0:
                words.setdefault(page, []).append((text, conf))
        out = []
        for page in range(1, n + 1):
            ws = words.get(page, [])
            if not ws:
                out.append(("", 0.0))
            else:
                out.append((" ".join(w for w, _ in ws), sum(c for _, c in ws) / len(ws)))
        return out
