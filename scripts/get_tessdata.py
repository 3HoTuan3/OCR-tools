"""Tải dữ liệu ngôn ngữ cho Tesseract vào thư mục tessdata/ của dự án.

    python scripts/get_tessdata.py              # vie + eng (bản "best", chính xác nhất)
    python scripts/get_tessdata.py --fast       # bản "fast": nhỏ & nhanh hơn, kém chính xác hơn chút
    python scripts/get_tessdata.py vie eng chi_sim chi_tra
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "tessdata"
BASE = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_{kind}/main/{lang}.traineddata"


def download(lang: str, kind: str) -> None:
    out = DEST / f"{lang}.traineddata"
    url = BASE.format(kind=kind, lang=lang)
    print(f"  {lang}: tải {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "ocrtool-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if len(data) < 100_000:
        raise RuntimeError(f"File {lang} quá nhỏ ({len(data)} byte), có thể tải lỗi.")
    tmp = out.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(out)
    print(f"      -> {out} ({len(data) / 1e6:.1f} MB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("langs", nargs="*", default=["vie", "eng"])
    ap.add_argument("--fast", action="store_true", help="dùng tessdata_fast thay vì tessdata_best")
    args = ap.parse_args()
    kind = "fast" if args.fast else "best"
    DEST.mkdir(exist_ok=True)
    failed = 0
    for lang in args.langs:
        if (DEST / f"{lang}.traineddata").exists():
            print(f"  {lang}: đã có, bỏ qua (xoá file để tải lại)")
            continue
        try:
            download(lang, kind)
        except Exception as exc:
            failed += 1
            print(f"  {lang}: LỖI {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
