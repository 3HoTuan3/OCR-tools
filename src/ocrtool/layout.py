"""Ghép các dòng OCR theo toạ độ: chế độ bảng (dán vào Excel/Sheets được) và gộp một dòng."""
from __future__ import annotations

from statistics import median

from .textutil import has_cjk


def _bbox(box) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def _clean(s: str) -> str:
    return " ".join(s.replace("\t", " ").split())


def _join(a: str, b: str) -> str:
    return a + b if (has_cjk(a[-1:]) or has_cjk(b[:1])) else a + " " + b


def lines_to_table(items) -> str:
    """items: danh sách (text, box). Trả về văn bản TSV: mỗi hàng một dòng, các ô cách nhau bằng Tab.

    Hàng: gom theo toạ độ y giữa dòng. Ô: các mảnh sát nhau (khoảng hở nhỏ) gộp lại, còn lại là ô riêng.
    Cột: gom theo mép trái của ô; hàng nào thiếu cột thì chèn ô trống để các cột thẳng hàng.
    """
    cells = []
    for text, box in items:
        text = _clean(text)
        if text:
            x0, y0, x1, y1 = _bbox(box)
            cells.append({"t": text, "x0": x0, "x1": x1, "cy": (y0 + y1) / 2, "h": max(1.0, y1 - y0)})
    if not cells:
        return ""
    mh = median(c["h"] for c in cells)

    rows: list[list[dict]] = []
    row_cy: list[float] = []
    for c in sorted(cells, key=lambda c: c["cy"]):
        if rows and abs(c["cy"] - row_cy[-1]) <= 0.6 * mh:
            rows[-1].append(c)
            row_cy[-1] = sum(x["cy"] for x in rows[-1]) / len(rows[-1])
        else:
            rows.append([c])
            row_cy.append(c["cy"])

    merged_rows: list[list[dict]] = []
    for row in rows:
        row.sort(key=lambda c: c["x0"])
        out = [dict(row[0])]
        for c in row[1:]:
            if c["x0"] - out[-1]["x1"] < 0.8 * mh:          # gần sát: cùng một ô
                out[-1]["t"] = _join(out[-1]["t"], c["t"])
                out[-1]["x1"] = max(out[-1]["x1"], c["x1"])
            else:
                out.append(dict(c))
        merged_rows.append(out)

    anchors: list[float] = []
    tol = 1.5 * mh
    for x in sorted(c["x0"] for row in merged_rows for c in row):
        if not anchors or x - anchors[-1] > tol:
            anchors.append(x)

    def col(x: float) -> int:
        return min(range(len(anchors)), key=lambda i: abs(anchors[i] - x))

    lines = []
    for row in merged_rows:
        slots: dict[int, str] = {}
        for c in row:
            k = col(c["x0"])
            slots[k] = (_join(slots[k], c["t"]) if k in slots else c["t"])
        last = max(slots)
        lines.append("\t".join(slots.get(i, "") for i in range(last + 1)))
    return "\n".join(lines)
