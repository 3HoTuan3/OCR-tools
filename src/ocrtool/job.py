"""Một lần chụp, chạy trong tiến trình riêng rồi thoát:  chọn vùng -> OCR -> chép chữ vào clipboard.

    python -m ocrtool.job --result kq.json --delay 250

Biểu tượng khay khởi động tiến trình này mỗi khi bấm. Engine OCR được nạp song song trong lúc bạn
đang kéo chọn vùng, nên sau khi thả chuột chỉ còn phần nhận dạng. Xong là tiến trình thoát và trả hết
RAM, khay hệ thống lúc rảnh chỉ là một app rất nhỏ.

Mã thoát: 0 = đã chép chữ, 2 = lỗi, 3 = người dùng huỷ, 4 = không thấy chữ (clipboard giữ nguyên).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from .config import Config, history_dir
from .layout import lines_to_table
from .textutil import has_cjk

EXIT_OK, EXIT_ERROR, EXIT_CANCELLED, EXIT_EMPTY = 0, 2, 3, 4
CODES = {"ok": EXIT_OK, "error": EXIT_ERROR, "cancelled": EXIT_CANCELLED, "empty": EXIT_EMPTY}


def join_text(lines: list[str], join: bool) -> str:
    if not join:
        return "\n".join(lines)
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and not (has_cjk(out[-1]) or has_cjk(ln[0])):
            out += " "
        out += ln
    return out


def compose_text(lines, cfg: Config) -> str:
    """Ghép các dòng OCR thành văn bản theo chế độ: bảng (Tab) / gộp một dòng / giữ xuống dòng."""
    if getattr(cfg, "table_mode", False):
        items = [(l.text, getattr(l, "box", None)) for l in lines]
        if items and all(b is not None for _t, b in items):
            return lines_to_table(items)
    return join_text([l.text for l in lines], cfg.join_lines)


def save_history(img, text: str, directory: Path, keep: int) -> None:
    """Lưu ảnh vùng chụp + chữ; chỉ giữ `keep` mục gần nhất."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    img.save(directory / f"{stem}.png")
    (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
    files = sorted(directory.glob("*.png"), key=lambda p: (p.stat().st_mtime, p.name))
    for old in files[:-max(1, keep)]:
        old.unlink(missing_ok=True)
        old.with_suffix(".txt").unlink(missing_ok=True)


def run_job(select, engine_factory, set_text, cfg: Config, hist_dir: Path | None = None) -> dict:
    """Lõi của một lần chụp (tách riêng để test).

    select()          -> PIL.Image | None   (chạy ở luồng chính, chặn tới khi người dùng chọn xong)
    engine_factory()  -> OCREngine          (chạy ở luồng nền, song song với select)
    set_text(text)    -> None
    """
    t0 = time.perf_counter()
    box: dict = {}

    def load():
        try:
            box["engine"] = engine_factory()
        except BaseException:  # noqa: BLE001
            box["error"] = traceback.format_exc()

    loader = threading.Thread(target=load, name="engine-loader", daemon=True)
    loader.start()

    img = select()
    if img is None:
        return {"status": "cancelled"}

    loader.join()
    if "error" in box:
        return {"status": "error", "message": "Không nạp được engine OCR:\n" + box["error"]}

    engine = box["engine"]
    engine.min_score = cfg.min_score
    res = engine.recognize(img)
    text = compose_text(res.lines, cfg)
    out = {"lines": len(res.lines), "chars": len(text), "warnings": list(res.warnings),
           "seconds": round(time.perf_counter() - t0, 2)}

    if cfg.keep_history:
        try:
            save_history(img, text, hist_dir or history_dir(), cfg.history_max)
        except Exception:
            out["warnings"].append("Không lưu được lịch sử: " + traceback.format_exc(limit=1))

    if not text.strip():
        return {"status": "empty", **out}

    set_text(text)
    snippet = " ".join(text.split())
    out["snippet"] = snippet[:90] + ("…" if len(snippet) > 90 else "")
    out["text"] = text                       # để cửa sổ kết quả/dịch của app khay dùng lại
    return {"status": "ok", **out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocrtool.job", description=__doc__.split("\n")[0])
    ap.add_argument("--result", help="ghi kết quả (JSON, UTF-8) vào file này")
    ap.add_argument("--delay", type=int, default=None, help="ms chờ trước khi chụp (mặc định theo cấu hình)")
    ap.add_argument("--toast", action="store_true", help="hiện thông báo nhỏ khi xong (khi chạy không có khay)")
    args = ap.parse_args(argv)

    started = time.monotonic()
    cfg = Config.load()
    delay = cfg.delay_ms if args.delay is None else args.delay

    def select():
        from .capture import grab_screen_region

        # chờ để menu/khay kịp đóng trước khi chụp màn hình
        wait = max(0.0, delay / 1000 - (time.monotonic() - started))
        return grab_screen_region(wait)

    def factory():
        from .engine import OCREngine
        return OCREngine(tess_lang=cfg.lang, min_score=cfg.min_score)

    from .clipboard import set_text

    try:
        result = run_job(select, factory, set_text, cfg)
    except Exception:
        result = {"status": "error", "message": traceback.format_exc()}

    if args.result:
        try:
            Path(args.result).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    try:
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        pass

    if args.toast and result["status"] != "cancelled":
        from .capture import show_toast
        msgs = {"ok": f"Đã chép {result.get('chars', 0)} ký tự — bấm Ctrl+V",
                "empty": "Không nhận ra chữ nào trong vùng đã chọn",
                "error": "OCR lỗi: " + str(result.get("message", "")).strip().splitlines()[-1][:120]}
        show_toast(msgs.get(result["status"], ""), 1800 if result["status"] == "ok" else 4000)
    return CODES.get(result["status"], EXIT_ERROR)


if __name__ == "__main__":
    sys.exit(main())
