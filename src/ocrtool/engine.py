"""Engine OCR lai: PaddleOCR PP-OCRv6 (qua RapidOCR/ONNX) + Tesseract.

Vì sao lai?
  * PP-OCRv6 dò vùng chữ rất tốt và đọc chuẩn tiếng Trung/Anh, nhưng từ điển của nó
    thiếu các chữ Việt có dấu chồng (ạ, ế, ệ, ỉ, ụ...), nên làm rơi chữ.
  * Tesseract (dữ liệu `vie`) đọc tiếng Việt đúng từng dấu, nhưng kém hơn với tiếng Trung.
  => PaddleOCR dò vị trí + đọc Trung/Anh; đoạn Latin/Việt được đọc lại bằng Tesseract.
     Dòng trộn Việt-Trung được tách theo tọa độ từng token để mỗi đoạn dùng đúng engine.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .tess import TesseractBackend, TesseractUnavailable
from .textutil import choose_latin, has_cjk, has_latin_letters

GAP_RATIO = 0.14  # khoảng trống > 14% chiều cao dòng thì coi là có dấu cách
_CLOSERS = set(")]}»,.;:!?，。：；！？）】」』")
_OPENERS = set("([{«（【「『")


# --------------------------------------------------------------------------- kiểu dữ liệu
@dataclass
class Line:
    text: str
    score: float                 # 0..1
    box: list                    # 4 điểm [[x,y],...] theo ảnh gốc
    source: str = "paddle"       # paddle | tesseract | mixed

    def to_dict(self) -> dict:
        return {"text": self.text, "score": round(self.score, 4),
                "box": [[round(float(x), 1), round(float(y), 1)] for x, y in self.box],
                "source": self.source}


@dataclass
class Result:
    lines: list[Line]
    elapsed: float
    scale: float = 1.0
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    def to_dict(self) -> dict:
        return {"text": self.text, "elapsed": round(self.elapsed, 3),
                "lines": [l.to_dict() for l in self.lines], "warnings": self.warnings}


@dataclass
class _Item:
    box: np.ndarray
    text: str
    score: float
    tokens: list | None  # [(text, conf, box4), ...]


@dataclass
class _Seg:
    kind: str            # "cjk" | "lat"
    text: str
    score: float
    x0: float
    x1: float
    job: int | None = None


# --------------------------------------------------------------------------- ảnh
def load_image(src) -> np.ndarray:
    """Nhận đường dẫn / PIL.Image / ndarray(BGR) -> ndarray BGR uint8."""
    if isinstance(src, np.ndarray):
        arr = src
        if arr.ndim == 2:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        return np.ascontiguousarray(arr[:, :, :3]).astype(np.uint8, copy=False)
    if isinstance(src, (str, Path)):
        img = Image.open(src)           # PIL mở được cả đường dẫn có dấu tiếng Việt trên Windows
        img.load()
    elif isinstance(src, Image.Image):
        img = src
    else:
        raise TypeError(f"Không hỗ trợ kiểu ảnh: {type(src)!r}")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, rgba)
    rgb = np.asarray(img.convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _norm(v) -> float:
    return float(np.hypot(v[0], v[1]))


def _line_height(box: np.ndarray) -> float:
    return max(_norm(box[3] - box[0]), _norm(box[2] - box[1]))


def crop_poly(img: np.ndarray, box: np.ndarray) -> np.ndarray:
    pts = box.astype(np.float32)
    w = max(1, int(round(max(_norm(pts[0] - pts[1]), _norm(pts[2] - pts[3])))))
    h = max(1, int(round(max(_norm(pts[0] - pts[3]), _norm(pts[1] - pts[2])))))
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    m = cv2.getPerspectiveTransform(pts, dst)
    out = cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    if h / w >= 1.5:  # dòng dọc: xoay ngang cho Tesseract
        out = np.ascontiguousarray(np.rot90(out))
    return out


def prep_for_tess(crop: np.ndarray) -> np.ndarray:
    """Chuẩn hoá ảnh một dòng cho Tesseract: xám, chiều cao ~48px, nền sáng, có viền."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h = gray.shape[0]
    if h < 48:
        f = min(4.0, 48.0 / max(h, 1))
    elif h > 100:
        f = 64.0 / h
    else:
        f = 1.0
    if abs(f - 1.0) > 1e-3:
        interp = cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=interp)
    if float(gray.mean()) < 110:        # chữ sáng trên nền tối -> đảo màu
        gray = 255 - gray
    edge = np.concatenate([gray[0, :], gray[-1, :]])
    bg = int(np.median(edge))
    return cv2.copyMakeBorder(gray, 12, 12, 16, 16, cv2.BORDER_CONSTANT, value=bg)


# --------------------------------------------------------------------------- engine
class OCREngine:
    """Dùng:  engine = OCREngine();  result = engine.recognize("anh.png");  print(result.text)"""

    def __init__(self, tesseract: bool = True, tess_lang: str = "vie+eng",
                 tessdata: str | None = None, auto_upscale: bool = True,
                 min_score: float = 0.0):
        from rapidocr import RapidOCR  # import chậm nên để trong hàm

        self.rapid = RapidOCR(params={"Global.log_level": "error"})
        self.auto_upscale = auto_upscale
        self.min_score = min_score
        self.warnings: list[str] = []
        self.tess: TesseractBackend | None = None
        if tesseract:
            try:
                self.tess = TesseractBackend.create(lang=tess_lang, tessdata=tessdata)
            except TesseractUnavailable as exc:
                self.warnings.append(
                    f"Không dùng được Tesseract ({exc}). Tiếng Việt có dấu chồng sẽ bị rơi chữ.")

    # ---------------------------------------------------------------- PaddleOCR
    def _paddle(self, img: np.ndarray) -> list[_Item]:
        r = self.rapid(img, return_word_box=True)
        if r is None or r.txts is None or len(r.txts) == 0:
            return []
        wr = getattr(r, "word_results", None)
        items = []
        for i, (box, txt, score) in enumerate(zip(r.boxes, r.txts, r.scores)):
            tokens = None
            if wr is not None and i < len(wr) and wr[i]:
                tokens = [(t, float(c), np.array(b, dtype=float)) for t, c, b in wr[i]]
            items.append(_Item(np.array(box, dtype=float), str(txt), float(score), tokens))
        return items

    # ---------------------------------------------------------------- công khai
    def recognize(self, source) -> Result:
        t0 = time.perf_counter()
        img = load_image(source)
        scale = 1.0
        items = self._paddle(img)
        if self.auto_upscale:
            med = statistics.median(_line_height(it.box) for it in items) if items else 0.0
            if (not items or med < 18) and max(img.shape[:2]) * 2 <= 5000:
                big = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                items2 = self._paddle(big)
                if items2:
                    img, items, scale = big, items2, 2.0

        lines = self._refine(img, items) if self.tess else [
            Line(it.text, it.score, it.box.tolist(), "paddle") for it in items]

        for ln in lines:
            ln.box = (np.array(ln.box, dtype=float) / scale).tolist()
        lines = [l for l in lines if l.text.strip() and l.score >= self.min_score]
        return Result(lines, time.perf_counter() - t0, scale, list(self.warnings))

    # ---------------------------------------------------------------- Tesseract
    def _segments(self, img: np.ndarray, it: _Item, jobs: list) -> list[_Seg] | None:
        """Tách dòng trộn thành các đoạn CJK / Latin dựa trên token của PaddleOCR."""
        if not it.tokens:
            return None
        groups: list[list] = []
        for tok in it.tokens:
            kind = "cjk" if has_cjk(tok[0]) else "lat"
            if groups and groups[-1][0] == kind:
                groups[-1][1].append(tok)
            else:
                groups.append([kind, [tok]])

        h, w = img.shape[:2]
        ys = it.box[:, 1]
        y0, y1 = int(max(0, ys.min())), int(min(h, np.ceil(ys.max())))
        lh = max(1.0, _line_height(it.box))
        bounds = []
        for kind, toks in groups:
            xs = np.concatenate([t[2][:, 0] for t in toks])
            bounds.append((float(xs.min()), float(xs.max())))

        segs: list[_Seg] = []
        for gi, (kind, toks) in enumerate(groups):
            x0, x1 = bounds[gi]
            text = ""
            for j, t in enumerate(toks):
                if j:
                    prev_x1 = toks[j - 1][2][:, 0].max()
                    gap = t[2][:, 0].min() - prev_x1
                    if gap > GAP_RATIO * lh and not (has_cjk(toks[j - 1][0]) and has_cjk(t[0])):
                        text += " "
                text += t[0]
            score = float(np.mean([t[1] for t in toks]))
            seg = _Seg(kind, text, score, x0, x1)
            if kind == "lat" and has_latin_letters(text):
                left = (bounds[gi - 1][1] + x0) / 2 if gi > 0 else 0.0
                right = (x1 + bounds[gi + 1][0]) / 2 if gi + 1 < len(groups) else float(w)
                # Phía giáp đoạn CJK chỉ chừa lề rất nhỏ để không lấy nhầm mảnh glyph kế bên.
                pad_l = 0.06 * lh if gi > 0 else 0.25 * lh
                pad_r = 0.06 * lh if gi + 1 < len(groups) else 0.25 * lh
                cx0 = int(max(left, x0 - pad_l, 0))
                cx1 = int(min(right, x1 + pad_r, w))
                if cx1 - cx0 >= 4 and y1 - y0 >= 4:
                    seg.job = len(jobs)
                    jobs.append(prep_for_tess(img[y0:y1, cx0:cx1]))
            segs.append(seg)
        return segs

    def _refine(self, img: np.ndarray, items: list[_Item]) -> list[Line]:
        jobs: list[np.ndarray] = []
        plans: list[tuple] = []
        for it in items:
            if not has_latin_letters(it.text):
                plans.append(("keep",))
            elif not has_cjk(it.text):
                plans.append(("line", len(jobs)))
                jobs.append(prep_for_tess(crop_poly(img, it.box)))
            else:
                segs = self._segments(img, it, jobs)
                plans.append(("mixed", segs) if segs else ("keep",))

        try:
            res = self.tess.recognize_batch(jobs) if jobs else []
        except Exception as exc:  # Tesseract lỗi giữa chừng -> quay về kết quả PaddleOCR
            self.warnings.append(f"Tesseract lỗi, dùng kết quả PaddleOCR: {exc}")
            res = [("", 0.0)] * len(jobs)

        lines: list[Line] = []
        for it, plan in zip(items, plans):
            box = it.box.tolist()
            if plan[0] == "keep":
                lines.append(Line(it.text, it.score, box, "paddle"))
            elif plan[0] == "line":
                tt, tc = res[plan[1]]
                text, src = choose_latin(it.text, it.score, tt, tc)
                score = tc / 100.0 if src == "tesseract" else it.score
                lines.append(Line(text, score, box, src))
            else:
                segs: list[_Seg] = plan[1]
                lh = max(1.0, _line_height(it.box))
                out, srcs, scores = "", set(), []
                for k, seg in enumerate(segs):
                    if seg.job is None:
                        txt, src, sc = seg.text, "paddle", seg.score
                    else:
                        tt, tc = res[seg.job]
                        txt, src = choose_latin(seg.text, seg.score, tt, tc)
                        sc = tc / 100.0 if src == "tesseract" else seg.score
                    txt = txt.strip() if seg.job is not None else txt
                    if (k and (seg.x0 - segs[k - 1].x1) > GAP_RATIO * lh
                            and txt[:1] not in _CLOSERS and out[-1:] not in _OPENERS):
                        out += " "
                    out += txt
                    srcs.add(src)
                    scores.append(sc)
                source = srcs.pop() if len(srcs) == 1 else "mixed"
                lines.append(Line(out, float(np.mean(scores)), box, source))
        return lines
