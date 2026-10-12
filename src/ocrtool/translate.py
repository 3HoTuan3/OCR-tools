"""Dịch văn bản sau khi OCR.

Hai công cụ:
  * "google" (mặc định): điểm cuối dịch công khai của Google, không cần khoá API, cần Internet.
    Chữ chỉ được gửi đi khi bạn bấm sang tab Dịch (hoặc chọn "Dịch ngay").
  * "argos": Argos Translate chạy offline (tuỳ chọn: pip install argostranslate; mô hình ngôn ngữ ~100 MB/cặp
    được tải một lần khi dùng lần đầu). Dịch qua tiếng Anh nếu không có cặp trực tiếp.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass

LANGS: dict[str, str] = {
    "vi": "Tiếng Việt", "en": "English", "zh-CN": "中文 (简体)", "zh-TW": "中文 (繁體)",
    "ja": "日本語", "ko": "한국어", "fr": "Français", "de": "Deutsch", "es": "Español",
    "pt": "Português", "ru": "Русский", "it": "Italiano", "th": "ไทย", "id": "Bahasa Indonesia",
}
ENGINES = {"google": "Google (cần Internet)", "argos": "Argos (offline, tuỳ chọn)"}

GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
CHUNK_CHARS = 3000
TIMEOUT_S = 15


class TranslateError(RuntimeError):
    """Lỗi dịch với thông báo tiếng Việt, hiện thẳng cho người dùng."""


@dataclass
class Translation:
    text: str
    source: str          # mã ngôn ngữ nguồn (do dịch vụ nhận ra hoặc đoán), "" nếu không rõ


def lang_name(code: str) -> str:
    return LANGS.get(code) or LANGS.get(_norm(code)) or code or "?"


def _norm(code: str) -> str:
    if code in LANGS:
        return code
    low = code.lower()
    if low in ("zh", "zh-cn", "zh-hans"):
        return "zh-CN"
    if low in ("zh-tw", "zh-hant"):
        return "zh-TW"
    return code.split("-")[0]


_VI_ONLY = set("ăâđêôơưĂÂĐÊÔƠƯ")
# từ chức năng hay gặp: nhận ra câu ngắn như "Xin chào" không có dấu hỏi/nặng
_VI_WORDS = {"xin", "chào", "và", "của", "là", "không", "một", "những", "được", "các", "tôi", "bạn", "này",
             "với", "trong", "có", "đã", "sẽ", "rất", "như", "để", "người", "việc", "cảm", "ơn", "cho", "khi",
             "nhà", "anh", "chị", "ông", "bà", "ở", "đây", "đó", "gì", "nào", "thì", "mà", "cũng", "nhiều"}


def detect_lang(text: str) -> str:
    """Đoán thô ngôn ngữ để chọn chiều dịch (không thay cho nhận dạng của dịch vụ)."""
    kana = hangul = han = cyr = thai = letters = 0
    vi_marks = 0
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:
            kana += 1
        elif 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
            hangul += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            han += 1
        elif 0x0400 <= o <= 0x04FF:
            cyr += 1
        elif 0x0E00 <= o <= 0x0E7F:
            thai += 1
        elif ch.isalpha():
            letters += 1
            if ch in _VI_ONLY:
                vi_marks += 1
    for ch in unicodedata.normalize("NFD", text):
        if ch in ("̉", "̣"):         # dấu hỏi, dấu nặng: đặc trưng tiếng Việt
            vi_marks += 1
    if _VI_WORDS & set(re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())):
        vi_marks += 1
    if kana:
        return "ja"
    if hangul:
        return "ko"
    if han:
        return "zh-CN"
    if cyr and cyr >= letters:
        return "ru"
    if thai:
        return "th"
    if vi_marks:
        return "vi"
    return "en" if letters else ""


def effective_target(text: str, target: str, fallback: str = "en") -> str:
    """Nếu chữ đã ở đúng ngôn ngữ đích thì dịch sang `fallback` (hoặc tiếng Việt nếu đích là tiếng Anh)."""
    det = detect_lang(text)
    if det and _norm(det).split("-")[0] == _norm(target).split("-")[0]:
        return fallback if _norm(target).split("-")[0] != fallback else "vi"
    return target


def _chunks(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    out, cur, size = [], [], 0
    for line in text.split("\n"):
        while len(line) > limit:                     # dòng quá dài: cắt cứng
            if cur:
                out.append("\n".join(cur)); cur, size = [], 0
            out.append(line[:limit]); line = line[limit:]
        if size + len(line) + 1 > limit and cur:
            out.append("\n".join(cur)); cur, size = [], 0
        cur.append(line); size += len(line) + 1
    if cur:
        out.append("\n".join(cur))
    return out


def _google_chunk(text: str, target: str, source: str) -> tuple[str, str]:
    params = {"client": "gtx", "sl": source, "tl": target, "dt": "t"}
    headers = {"User-Agent": "Mozilla/5.0"}
    body = urllib.parse.urlencode({**params, "q": text})
    if len(body) < 1800:
        req = urllib.request.Request(f"{GOOGLE_URL}?{body}", headers=headers)
    else:
        req = urllib.request.Request(
            f"{GOOGLE_URL}?{urllib.parse.urlencode(params)}", data=urllib.parse.urlencode({"q": text}).encode(),
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise TranslateError("Dịch vụ dịch đang giới hạn tần suất (HTTP 429). Đợi một lúc rồi thử lại.") from exc
        raise TranslateError(f"Dịch vụ dịch trả lỗi HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TranslateError("Không kết nối được tới dịch vụ dịch. Kiểm tra Internet rồi thử lại.") from exc
    except ValueError as exc:
        raise TranslateError("Dịch vụ dịch trả về dữ liệu không đọc được.") from exc
    try:
        out = "".join(seg[0] for seg in payload[0] if seg and seg[0])
        detected = payload[2] if len(payload) > 2 and isinstance(payload[2], str) else ""
    except (TypeError, IndexError, KeyError) as exc:
        raise TranslateError("Dịch vụ dịch trả về định dạng lạ.") from exc
    return out, detected


def _google(text: str, target: str, source: str) -> Translation:
    parts, detected = [], ""
    for chunk in _chunks(text):
        if not chunk.strip():
            parts.append(chunk)
            continue
        out, det = _google_chunk(chunk, target, source)
        parts.append(out.rstrip("\n") if not chunk.endswith("\n") else out)
        detected = detected or det
    return Translation("\n".join(parts), detected or (detect_lang(text) if source == "auto" else source))


# ---------------------------------------------------------------- Argos (offline, tuỳ chọn)
def argos_available() -> bool:
    try:
        import argostranslate.translate  # noqa: F401
        return True
    except Exception:
        return False


def _argos_code(code: str) -> str:
    code = _norm(code)
    return {"zh-CN": "zh", "zh-TW": "zt"}.get(code, code.split("-")[0])


def _argos_pair_ready(T, a: str, b: str) -> bool:
    langs = {l.code: l for l in T.get_installed_languages()}
    return a in langs and b in langs and langs[a].get_translation(langs[b]) is not None


def _argos(text: str, target: str, source: str) -> Translation:
    if not argos_available():
        raise TranslateError("Chưa cài Argos Translate. Chạy:  .venv\\Scripts\\pip install argostranslate")
    import argostranslate.package as P
    import argostranslate.translate as T

    src = _argos_code(source if source != "auto" else (detect_lang(text) or "en"))
    dst = _argos_code(target)
    if src == dst:
        return Translation(text, src)
    pairs = [(src, dst)] if "en" in (src, dst) else [(src, "en"), ("en", dst)]
    try:
        missing = [p for p in pairs if not _argos_pair_ready(T, *p)]
        if missing:
            P.update_package_index()                 # cần mạng, chỉ lần đầu cho mỗi cặp
            available = P.get_available_packages()
            for a, b in missing:
                pkg = next((p for p in available if p.from_code == a and p.to_code == b), None)
                if pkg is None:
                    raise TranslateError(f"Argos chưa có mô hình dịch {a} → {b}.")
                P.install_from_path(pkg.download())
        out = T.translate(text, src, dst)
    except TranslateError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TranslateError(f"Argos lỗi: {exc}") from exc
    return Translation(out, src)


# ---------------------------------------------------------------- công khai
_cache: "OrderedDict[tuple, Translation]" = OrderedDict()
_cache_lock = threading.Lock()


def translate(text: str, target: str, source: str = "auto", engine: str = "google") -> Translation:
    """Dịch `text` sang `target` (mã trong LANGS). Có bộ nhớ đệm 64 mục. Ném TranslateError khi lỗi."""
    text = text.strip("\r\n")
    if not text.strip():
        return Translation("", "")
    key = (engine, source, target, text)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if engine == "argos":
        result = _argos(text, target, source)
    elif engine == "google":
        result = _google(text, target, source)
    else:
        raise TranslateError(f"Công cụ dịch không hợp lệ: {engine}")
    with _cache_lock:
        _cache[key] = result
        while len(_cache) > 64:
            _cache.popitem(last=False)
    return result
