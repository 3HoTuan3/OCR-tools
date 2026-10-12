"""Ghi chữ vào clipboard (Windows: CF_UNICODETEXT nên Win+V lưu vào lịch sử clipboard và Ctrl+V dán được)."""
from __future__ import annotations

import time


def set_text(text: str, retries: int = 6) -> None:
    """Chép `text` vào clipboard; thử lại vài lần vì app khác có thể đang giữ clipboard."""
    import pyperclip

    last: Exception | None = None
    for _ in range(retries):
        try:
            pyperclip.copy(text)
            return
        except Exception as exc:          # clipboard bận / thiếu xclip
            last = exc
            time.sleep(0.1)
    raise RuntimeError(f"Không ghi được vào clipboard: {last}")
