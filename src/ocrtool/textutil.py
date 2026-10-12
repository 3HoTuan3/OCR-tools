"""Hàm tiện ích xử lý văn bản: nhận diện chữ Hán/Nhật/Hàn, so khớp không dấu,
và chọn kết quả tốt hơn giữa hai engine OCR."""
from __future__ import annotations

import difflib
import re
import unicodedata

_CJK_RANGES = (
    (0x1100, 0x11FF),    # Hangul Jamo
    (0x2E80, 0x2FDF),    # CJK radicals
    (0x3000, 0x30FF),    # CJK punctuation, Hiragana, Katakana
    (0x3100, 0x31FF),    # Bopomofo, Hangul compat, Kanbun
    (0x3400, 0x4DBF),    # CJK Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0xAC00, 0xD7AF),    # Hangul syllables
    (0xF900, 0xFAFF),    # CJK compatibility ideographs
    (0xFE30, 0xFE4F),    # CJK compatibility forms
    (0xFF00, 0xFFEF),    # Fullwidth forms
    (0x20000, 0x2FA1F),  # CJK Extension B..F
)


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in _CJK_RANGES)


def has_cjk(text: str) -> bool:
    return any(is_cjk(c) for c in text)


def has_latin_letters(text: str) -> bool:
    """True nếu có chữ cái không thuộc nhóm CJK (Latin, Việt có dấu, Cyrillic...)."""
    return any(c.isalpha() and not is_cjk(c) for c in text)


def fold(text: str) -> str:
    """Bỏ dấu, bỏ khoảng trắng/dấu câu, về chữ thường: dùng để so sánh hai kết quả OCR."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"[\W_]+", "", text)


def similarity(a: str, b: str) -> float:
    fa, fb = fold(a), fold(b)
    if not fa and not fb:
        return 1.0
    return difflib.SequenceMatcher(None, fa, fb, autojunk=False).ratio()


def coverage(sub: str, full: str) -> float:
    """Tỉ lệ ký tự (đã bỏ dấu) của `sub` xuất hiện, đúng thứ tự, trong `full`.
    PaddleOCR hay làm rơi chữ Việt dấu chồng, nên bản của nó thường là "tập con" của bản Tesseract."""
    fs, ff = fold(sub), fold(full)
    if not fs:
        return 0.0
    sm = difflib.SequenceMatcher(None, fs, ff, autojunk=False)
    return sum(m.size for m in sm.get_matching_blocks()) / len(fs)


_KEEP_EDGE = set("–—…“”‘’«»€£¥")
_JUNK_CATS = {"So", "Sk", "Sm", "Po", "Pi", "Pf", "Pc", "Pd"}


def strip_edge_junk(text: str) -> str:
    """Bỏ ký tự rác ngoài ASCII (¡ ° ® ...) ở hai đầu: thường là mảnh glyph của đoạn kế bên
    lọt vào vùng cắt. Chữ Việt thật chỉ gồm chữ cái, chữ số và dấu câu ASCII nên an toàn."""
    def junk(c: str) -> bool:
        return ord(c) > 127 and c not in _KEEP_EDGE and unicodedata.category(c) in _JUNK_CATS

    s = text.strip()
    while s and junk(s[0]):
        s = s[1:].lstrip()
    while s and junk(s[-1]):
        s = s[:-1].rstrip()
    return s


def _is_punct(c: str) -> bool:
    return not c.isalnum() and not c.isspace()


def trim_stray_edge(tess_text: str, paddle_text: str) -> str:
    """Bỏ dấu câu thừa ở hai đầu do mảnh glyph kế bên lọt vào vùng cắt, vd "đ (;" -> "đ (".
    Chỉ bỏ khi đó là dấu câu đứng cạnh một dấu câu khác và PaddleOCR không thấy dấu đó."""
    s = tess_text.strip()
    p = paddle_text.strip()
    while len(s) > 1 and _is_punct(s[-1]) and _is_punct(s[:-1].rstrip()[-1:] or "a") \
            and (not p or s[-1] != p[-1]):
        s = s[:-1].rstrip()
    while len(s) > 1 and _is_punct(s[0]) and _is_punct(s[1:].lstrip()[:1] or "a") \
            and (not p or s[0] != p[0]):
        s = s[1:].lstrip()
    return s


def choose_latin(paddle_text: str, paddle_score: float, tess_text: str, tess_conf: float):
    """Chọn giữa kết quả PaddleOCR và Tesseract cho một đoạn chữ Latin/Việt.

    - Hai bên "đồng ý" về các chữ cái (chỉ khác dấu): lấy Tesseract vì giữ đủ dấu tiếng Việt.
    - Hai bên bất đồng hẳn: tin bên có độ tin cậy cao hơn (tess_conf theo thang 0-100).

    Trả về (text, source) với source là "tesseract" hoặc "paddle".
    """
    p = paddle_text.strip()
    t = trim_stray_edge(strip_edge_junk(tess_text), p)
    if not t:
        return paddle_text, "paddle"
    if not p:
        return t, "tesseract"
    if similarity(p, t) >= 0.80 or coverage(p, t) >= 0.85:
        return t, "tesseract"
    if tess_conf / 100.0 > paddle_score:
        return t, "tesseract"
    return paddle_text, "paddle"
