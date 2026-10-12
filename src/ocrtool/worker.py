"""Tiến trình OCR thường trực: nạp engine một lần, nhận yêu cầu qua stdin, trả kết quả qua stdout (JSON mỗi dòng).

App nền khởi động tiến trình này khi cần và tự cho nó thoát sau một thời gian không dùng để trả RAM.
Giao thức (mỗi dòng một JSON):
    -> {"id": 1, "op": "warm", "lang": "vie+eng"}
    -> {"id": 2, "op": "ocr", "path": "...png", "lang": "vie+eng", "min_score": 0.0}
    <- {"id": 2, "ok": true, "lines": [{"text", "score", "box", "source"}], "warnings": [...], "seconds": 0.8}
    <- {"id": n, "ok": false, "error": "..."}
    -> {"op": "quit"}     (hoặc đóng stdin)
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback


def _streams():
    inp = sys.stdin.buffer if sys.stdin is not None else os.fdopen(0, "rb")
    out = sys.stdout.buffer if sys.stdout is not None else os.fdopen(1, "wb")
    sys.stdout = sys.stderr            # mọi print lạc không được làm hỏng giao thức
    return inp, out


def main() -> int:
    inp, out = _streams()
    engine = None
    engine_lang = None

    def send(msg: dict) -> None:
        out.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        out.flush()

    def get_engine(lang: str):
        nonlocal engine, engine_lang
        if engine is None or engine_lang != lang:
            from .engine import OCREngine
            engine = OCREngine(tess_lang=lang, warmup=True)
            engine_lang = lang
        return engine

    for raw in inp:
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        op, rid = req.get("op"), req.get("id")
        if op == "quit":
            break
        t0 = time.perf_counter()
        try:
            eng = get_engine(req.get("lang") or "vie+eng")
            if op == "warm":
                send({"id": rid, "ok": True, "seconds": round(time.perf_counter() - t0, 3)})
            elif op == "ocr":
                eng.min_score = float(req.get("min_score", 0.0))
                res = eng.recognize(req["path"])
                send({"id": rid, "ok": True, "lines": [l.to_dict() for l in res.lines],
                      "warnings": list(res.warnings), "seconds": round(time.perf_counter() - t0, 3)})
            else:
                send({"id": rid, "ok": False, "error": f"op lạ: {op}"})
        except Exception:
            send({"id": rid, "ok": False, "error": traceback.format_exc()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
