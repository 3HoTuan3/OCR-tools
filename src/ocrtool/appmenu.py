"""Dựng nội dung menu chuột phải của cửa sổ nổi (tách riêng khỏi giao diện để dễ test)."""
from __future__ import annotations

import sys

from . import translate as tr
from .menu import SEP, MenuItem

SIZES = (("Nhỏ", 36), ("Vừa", 48), ("Lớn", 64))
OPACITIES = (("100%", 1.0), ("75%", 0.75), ("50%", 0.5), ("30%", 0.3))
AFTER = (("window", "Hiện cửa sổ kết quả (bắt chữ / dịch)"), ("translate", "Dịch ngay sau khi chụp"),
         ("copy", "Chỉ chép chữ, không hiện cửa sổ"))
DEFAULT_HOTKEY = "ctrl+alt+o"
KEEP = ((-1, "Luôn giữ (nhanh nhất, ~250 MB RAM)"), (15, "15 phút sau lần dùng cuối"), (5, "5 phút"),
        (0, "Không giữ (tiết kiệm RAM, chậm hơn)"))


def output_mode(cfg) -> str:
    return "table" if cfg.table_mode else ("single" if cfg.join_lines else "lines")


def build_menu(app) -> list[MenuItem]:
    cfg = app.cfg
    M = MenuItem

    def radio(options, current, setter):
        return [M(label=label, checked=(key == current), action=lambda k=key: setter(k)) for key, label in options]

    hist = app.history_items()
    history_children = [M(label=label, action=lambda p=path: app.copy_history(p)) for label, path in hist]
    if history_children:
        history_children.append(SEP)
    history_children += [
        M(label="Lưu lịch sử ảnh + chữ", icon="", checked=cfg.keep_history,
          action=lambda: app.toggle("keep_history")),
        M(label="Mở thư mục lịch sử", action=app.open_history),
    ]

    mode = output_mode(cfg)
    out_children = radio((("lines", "Giữ xuống dòng như trong ảnh"), ("single", "Gộp thành một đoạn"),
                          ("table", "Bảng (dán vào Excel, các ô cách bằng Tab)")), mode, app.set_output_mode)

    langs = [M(label=name, checked=(code == cfg.target_lang), action=lambda c=code: app.set_option("target_lang", c))
             for code, name in tr.LANGS.items()]
    engines = []
    for key, label in tr.ENGINES.items():
        ok = key != "argos" or tr.argos_available()
        engines.append(M(label=label + ("" if ok else " — chưa cài"), checked=(key == cfg.translate_engine),
                         enabled=ok, action=lambda k=key: app.set_option("translate_engine", k)))
    engines += [SEP, M(label="Tự chép chữ của tab đang xem", checked=cfg.translate_autocopy,
                       action=lambda: app.toggle("translate_autocopy"))]

    float_children = [
        M(label="Kích thước", icon="", children=[
            M(label=n, checked=(cfg.float_size == v), action=lambda v=v: app.set_option("float_size", v))
            for n, v in SIZES]),
        M(label="Độ trong suốt khi nghỉ", children=[
            M(label=n, checked=(abs(cfg.float_opacity - v) < 0.01),
              action=lambda v=v: app.set_option("float_opacity", float(v))) for n, v in OPACITIES]),
        M(label="Luôn ở trên cùng", checked=cfg.float_topmost, action=lambda: app.toggle("float_topmost")),
        M(label="Đưa về góc màn hình", action=app.reset_position),
    ]

    hot_ok = sys.platform == "win32"
    items = [
        M(label="Chụp vùng để OCR", icon="▣", action=app.capture, accent=True),
        M(label="Lăng kính dịch", icon="◫", checked=app.lens is not None, hint="Shift+bấm",
          action=app.toggle_lens),
        SEP,
        M(label="Sau khi chụp", icon="↳",
          children=radio(AFTER, cfg.after_capture, lambda k: app.set_option("after_capture", k))),
        M(label=f"Dịch sang: {tr.lang_name(cfg.target_lang)}", icon="文", children=langs),
        M(label="Công cụ dịch", icon="⇄", children=engines),
        M(label="Kiểu chữ xuất ra", icon="≡", children=out_children),
        SEP,
        M(label="Giữ engine OCR sẵn sàng", icon="⚡",
          children=radio(KEEP, cfg.keep_engine_min, lambda k: app.set_option("keep_engine_min", k))),
        M(label=f"Lịch sử ({len(hist)})", icon="↺", children=history_children),
        M(label="Cài đặt cửa sổ nổi", icon="⚙", children=float_children),
        M(label="Thông báo khi chép xong", icon="◔", checked=cfg.notify, action=lambda: app.toggle("notify")),
        M(label="Phím tắt toàn cục", icon="⌨", checked=bool(cfg.hotkey) if hot_ok else None, enabled=hot_ok,
          hint=("Ctrl+Alt+O / L" if hot_ok else "chỉ Windows"), action=app.toggle_hotkey),
        M(label="Khởi động cùng máy", icon="⚑", checked=app.autostart_enabled(), action=app.toggle_autostart),
        M(label="Mở file log", icon="▤", action=app.open_log),
        SEP,
        M(label="Ẩn cửa sổ nổi", icon="⊘", enabled=app.tray_ok, hint=("" if app.tray_ok else "cần khay"),
          action=app.hide_widget),
        M(label="Thoát", icon="⏻", action=app.quit),
    ]
    return items
