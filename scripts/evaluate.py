"""Đo độ chính xác (CER = tỉ lệ ký tự sai) trên samples/*.png so với samples/*.txt.

    python scripts/evaluate.py                # mọi ảnh trong samples/
    python scripts/evaluate.py anh1.png ...   # cần file .txt đáp án cùng tên

So sánh: PaddleOCR đơn lẻ  vs  bản lai (PaddleOCR + Tesseract). Bỏ qua khoảng trắng và
các kiểu gạch ngang/ngoặc kép khác nhau (– — - ).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import re
import unicodedata

from ocrtool import OCREngine  # noqa: E402


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", "", s)


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    return edit_distance(r, h) / max(1, len(r))


def peak_rss_mb() -> float | None:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KB
    except Exception:
        pass
    try:
        import psutil
        return psutil.Process().memory_info().peak_wset / 1e6  # Windows
    except Exception:
        return None


def main() -> None:
    given = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = [Path(a) for a in given] or sorted((ROOT / "samples").glob("*.png"))
    files = [f for f in files if f.with_suffix(".txt").exists()]
    if not files:
        sys.exit("Không có ảnh nào kèm file .txt đáp án.")

    modes = {"Paddle": OCREngine(tesseract=False), "Lai   ": OCREngine(tesseract=True)}
    for eng in modes.values():
        for w in eng.warnings:
            print("cảnh báo:", w)
    print(f"{'ảnh':<22}{'Paddle CER':>12}{'Lai CER':>10}{'t(Lai)':>9}")
    tot = {k: [0, 0] for k in modes}
    for f in files:
        ref = f.with_suffix(".txt").read_text(encoding="utf-8")
        row = []
        for name, eng in modes.items():
            t = time.perf_counter()
            res = eng.recognize(f)
            dt = time.perf_counter() - t
            c = cer(ref, res.text)
            row.append((c, dt, res.text))
            tot[name][0] += edit_distance(norm(ref), norm(res.text))
            tot[name][1] += len(norm(ref))
        print(f"{f.name:<22}{row[0][0]*100:>11.1f}%{row[1][0]*100:>9.1f}%{row[1][1]:>8.2f}s")
        if "-v" in sys.argv:
            print("  ĐÁP ÁN:", ref.replace("\n", " | "))
            print("  LAI   :", row[1][2].replace("\n", " | "))
    print("-" * 53)
    print(f"{'TỔNG':<22}" + "".join(f"{tot[k][0]/max(1,tot[k][1])*100:>11.1f}%" if i == 0
                                     else f"{tot[k][0]/max(1,tot[k][1])*100:>9.1f}%"
                                     for i, k in enumerate(modes)))
    rss = peak_rss_mb()
    if rss:
        print(f"RAM đỉnh của tiến trình: {rss:.0f} MB")


if __name__ == "__main__":
    main()
