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
    delay_ms: int = 250           # chờ trước khi chụp để menu khay kịp đóng

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
