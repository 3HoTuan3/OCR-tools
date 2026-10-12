"""ocrtool - OCR nhẹ, chạy offline cho tiếng Việt, Anh, Trung (Windows & Linux)."""
from .engine import Line, OCREngine, Result, load_image

__all__ = ["OCREngine", "Result", "Line", "load_image"]
__version__ = "0.1.0"
