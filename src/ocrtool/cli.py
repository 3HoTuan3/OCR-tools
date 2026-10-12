"""Giao diện dòng lệnh:  python -m ocrtool anh.png   |   --screen   |   --clipboard"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _doctor() -> int:
    from . import __version__
    from .tess import TesseractBackend, find_executable, project_tessdata

    print(f"ocrtool {__version__} | Python {sys.version.split()[0]} | {sys.platform}")
    try:
        import rapidocr
        import onnxruntime
        print(f"[ok] rapidocr {getattr(rapidocr, '__version__', '?')}, onnxruntime {onnxruntime.__version__}")
    except Exception as exc:
        print(f"[!!] thiếu rapidocr/onnxruntime: {exc}")
        return 1
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
    print("Mọi thứ sẵn sàng.")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="ocr", description="OCR offline cho tiếng Việt, Anh, Trung (PaddleOCR v6 + Tesseract).")
    ap.add_argument("images", nargs="*", help="đường dẫn ảnh")
    ap.add_argument("-s", "--screen", action="store_true", help="kéo chọn một vùng màn hình để OCR")
    ap.add_argument("-c", "--clipboard", action="store_true",
                    help="OCR ảnh đang trong clipboard (vd. sau Win+Shift+S)")
    ap.add_argument("--copy", action="store_true", help="chép kết quả vào clipboard")
    ap.add_argument("--notify", action="store_true", help="hiện thông báo nhỏ khi xong (dùng với --copy)")
    ap.add_argument("--json", action="store_true", help="in JSON (kèm toạ độ, độ tin cậy, nguồn)")
    ap.add_argument("-o", "--output", help="ghi kết quả ra file (UTF-8)")
    ap.add_argument("--no-tesseract", action="store_true", help="chỉ dùng PaddleOCR (mất dấu chồng tiếng Việt)")
    ap.add_argument("--lang", default="vie+eng", help="ngôn ngữ Tesseract cho chữ Latin (mặc định vie+eng)")
    ap.add_argument("--tessdata", help="thư mục chứa *.traineddata")
    ap.add_argument("--min-score", type=float, default=0.0, help="bỏ dòng có độ tin cậy thấp hơn (0-1)")
    ap.add_argument("--no-upscale", action="store_true", help="tắt tự phóng ảnh khi chữ quá nhỏ")
    ap.add_argument("-v", "--verbose", action="store_true", help="in thời gian và cảnh báo")
    ap.add_argument("--doctor", action="store_true", help="kiểm tra cài đặt")
    args = ap.parse_args(argv)

    if args.doctor:
        return _doctor()
    try:
        return _run(args, ap)
    except Exception as exc:
        if args.notify:
            from .capture import show_toast
            show_toast(f"OCR lỗi: {exc}", 4000)
        raise


def _run(args, ap) -> int:
    from .capture import CaptureError, grab_clipboard_image, grab_screen_region
    from .engine import OCREngine

    sources: list[tuple[str, object]] = []
    try:
        if args.screen:
            img = grab_screen_region()
            if img is None:
                print("Đã huỷ.", file=sys.stderr)
                return 1
            sources.append(("màn hình", img))
        if args.clipboard:
            sources.append(("clipboard", grab_clipboard_image()))
    except CaptureError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    for p in args.images:
        if not Path(p).exists():
            print(f"Lỗi: không thấy file {p}", file=sys.stderr)
            return 2
        sources.append((p, p))
    if not sources:
        ap.print_help()
        return 2

    engine = OCREngine(tesseract=not args.no_tesseract, tess_lang=args.lang,
                       tessdata=args.tessdata, auto_upscale=not args.no_upscale,
                       min_score=args.min_score)

    chunks, payload = [], []
    for name, src in sources:
        res = engine.recognize(src)
        if args.json:
            payload.append({"source": name, **res.to_dict()})
        else:
            chunks.append((f"=== {name} ===\n" if len(sources) > 1 else "") + res.text)
        if args.verbose:
            print(f"[{name}] {len(res.lines)} dòng, {res.elapsed:.2f}s, scale x{res.scale:g}",
                  file=sys.stderr)
    if args.verbose:
        for w in engine.warnings:
            print(f"[cảnh báo] {w}", file=sys.stderr)

    out = (json.dumps(payload if len(payload) > 1 else payload[0], ensure_ascii=False, indent=2)
           if args.json else "\n\n".join(chunks))
    print(out)
    if args.output:
        Path(args.output).write_text(out + "\n", encoding="utf-8")
    if args.copy:
        text = out if not args.json else "\n".join(r["text"] for r in payload)
        try:
            import pyperclip
            pyperclip.copy(text)
            print("(đã chép vào clipboard)", file=sys.stderr)
            if args.notify:
                from .capture import show_toast
                show_toast(f"Đã chép {len(text)} ký tự vào clipboard" if text.strip()
                           else "Không nhận ra chữ nào")
        except Exception as exc:
            print(f"Không chép được vào clipboard: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
