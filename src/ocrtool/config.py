"""Cấu hình và thư mục dữ liệu của app khay hệ thống."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def app_dir() -> Path:
    """Windows: %LOCALAPPDATA%\\ocrtool   Linux: ~/.local/state/ocrtool"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    d = Path(base) / "ocrtool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def history_dir() -> Path:
    d = app_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    return app_dir() / "ocrtool.log"


@dataclass
class Config:
    notify: bool = True           # hiện thông báo khi xong
    keep_history: bool = True     # lưu ảnh vùng chụp + chữ để xem lại
    history_max: int = 20
    join_lines: bool = False      # gộp các dòng thành một đoạn
    lang: str = "vie+eng"         # ngôn ngữ Tesseract cho chữ Latin
    min_score: float = 0.0
    delay_ms: int = 250           # chờ trước khi chụp để menu/cửa sổ nổi kịp ẩn
    table_mode: bool = False      # xuất dạng bảng (Tab giữa các ô) để dán vào Excel
    # --- sau khi chụp
    after_capture: str = "window"  # copy = chỉ chép | window = hiện cửa sổ kết quả | translate = dịch ngay
    target_lang: str = "vi"        # ngôn ngữ đích khi dịch (xem translate.LANGS)
    translate_engine: str = "google"
    translate_autocopy: bool = True  # chép chữ của tab đang xem (gốc/dịch) vào clipboard
    # --- cửa sổ nổi
    float_visible: bool = True
    float_x: int = -1              # -1 = vị trí mặc định (góc dưới phải)
    float_y: int = -1
    float_size: int = 48
    float_opacity: float = 1.0     # độ đục khi không rê chuột vào (0.3 .. 1.0)
    float_topmost: bool = True
    hotkey: str = ""               # vd. "ctrl+alt+o"; rỗng = tắt (chỉ Windows)

    @classmethod
    def path(cls) -> Path:
        return app_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            for key, value in data.items():
                # bỏ qua khoá cũ/lạ và giá trị sai kiểu (bool không được lẫn với int)
                if key in known and type(value) is type(getattr(cfg, key)):
                    setattr(cfg, key, value)
        except Exception:
            pass
        return cfg

    def save(self) -> None:
        try:
            self.path().write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            pass
