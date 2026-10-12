"""Kiểm tra cài đặt:  python -m ocrtool   (hoặc  python -m ocrtool.doctor)"""
from __future__ import annotations

import sys


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    from . import __version__
    from .tess import TesseractBackend, find_executable, project_tessdata

    ok = True
    print(f"ocrtool {__version__} | Python {sys.version.split()[0]} | {sys.platform}")
    try:
        import onnxruntime
        import rapidocr
        print(f"[ok] rapidocr {getattr(rapidocr, '__version__', '?')}, onnxruntime {onnxruntime.__version__}")
    except Exception as exc:
        print(f"[!!] thiếu rapidocr/onnxruntime: {exc}")
        return 1

    for mod, hint in (("tkinter", "Python cần cài kèm Tcl/Tk (Linux: sudo apt install python3-tk)"),
                      ("pystray", "pip install pystray"), ("mss", "pip install mss"),
                      ("pyperclip", "pip install pyperclip")):
        try:
            __import__(mod)
            print(f"[ok] {mod}")
        except Exception as exc:
            ok = False
            print(f"[!!] thiếu {mod} ({exc}). {hint}")

    exe = find_executable()
    if not exe:
        print("[!!] Không tìm thấy Tesseract (cần cho tiếng Việt có dấu).\n"
              "     Windows: winget install -e --id UB-Mannheim.TesseractOCR\n"
              "     Linux:   sudo apt install tesseract-ocr")
        return 1
    td = project_tessdata()
    backend = TesseractBackend(exe, tessdata=td)
    langs = backend.available_langs()
    print(f"[ok] {backend.version()}  ({exe})")
    print(f"     tessdata: {td or '(mặc định của Tesseract)'}  ngôn ngữ: {', '.join(sorted(langs))}")
    if "vie" not in langs:
        print("[!!] Thiếu dữ liệu 'vie'. Chạy: python scripts/get_tessdata.py")
        return 1
    print("Mọi thứ sẵn sàng." if ok else "Còn thiếu một số thành phần ở trên.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
