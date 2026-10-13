"""Tạo lại các file icon trong src/ocrtool/assets/ (chỉ cần khi đổi icon; app dùng file PNG/ICO đã tạo sẵn).

Nguồn:
  * Icon menu/nút: Fluent UI System Icons của Microsoft (giấy phép MIT) — gói npm @fluentui/svg-icons.
  * Logo app: vẽ riêng cho dự án (LOGO_SVG bên dưới).

Cách chạy:  npm pack @fluentui/svg-icons && tar xzf fluentui-svg-icons-*.tgz
            pip install cairosvg
            python scripts/build_icons.py package/icons
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src" / "ocrtool" / "assets"

# tên trong app -> tên icon Fluent (cỡ 24, nét "regular")
ICONS = {
    "capture": "scan_text", "lens": "glasses", "after": "arrow_routing", "translate": "translate",
    "engine": "globe", "output": "text_align_left", "keep": "flash", "history": "history",
    "settings": "settings", "notify": "alert", "hotkey": "keyboard", "autostart": "rocket",
    "log": "document_text", "hide": "eye_off", "quit": "power", "copy": "copy", "pause": "pause",
    "play": "play", "close": "dismiss", "mode": "arrow_swap", "check": "checkmark", "chevron": "chevron_right",
}

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="#6d28d9"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <g fill="none" stroke="#ffffff" stroke-width="16" stroke-linecap="round" stroke-linejoin="round">
    <path d="M52 92 V68 a16 16 0 0 1 16 -16 H92"/>
    <path d="M164 52 H188 a16 16 0 0 1 16 16 V92"/>
    <path d="M52 164 V188 a16 16 0 0 0 16 16 H92"/>
    <path d="M204 164 V188 a16 16 0 0 1 -16 16 H164"/>
  </g>
  <g fill="#ffffff">
    <rect x="82" y="90" width="92" height="16" rx="8"/>
    <rect x="82" y="120" width="64" height="16" rx="8" opacity="0.85"/>
    <rect x="82" y="150" width="80" height="16" rx="8" opacity="0.7"/>
  </g>
  <circle cx="186" cy="150" r="26" fill="#fbbf24"/>
  <path d="M174 140 h24 M186 134 v6 M178 140 c2 10 10 18 20 20 M194 140 c-2 10 -10 18 -20 20" stroke="#1e1b4b"
        stroke-width="5" fill="none" stroke-linecap="round"/>
</svg>"""


def small_logo() -> str:
    """Bản cho cỡ <= 24px: bỏ huy hiệu 文 (quá nhỏ sẽ thành chấm nhoè)."""
    s = LOGO_SVG
    a = s.index('  <circle cx="186"')
    b = s.index("</svg>")
    return s[:a] + s[b:]


def render(svg: str, size: int):
    import cairosvg
    from PIL import Image

    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main(src_dir: str) -> None:
    src = Path(src_dir)
    out = ASSETS / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for name, fluent in ICONS.items():
        svg = (src / f"{fluent}_24_regular.svg").read_text(encoding="utf-8")
        svg = svg.replace("<svg ", '<svg fill="#ffffff" ', 1)          # icon trắng, app tự tô màu khi dùng
        render(svg, 48).save(out / f"{name}.png", optimize=True)
    logo = render(LOGO_SVG, 256)
    logo.save(ASSETS / "app.png", optimize=True)
    for s in (16, 24, 32, 48, 64):
        render(LOGO_SVG if s > 24 else small_logo(), s).save(ASSETS / f"app_{s}.png", optimize=True)
    # .ico nhiều cỡ: cỡ nhỏ dùng bản không huy hiệu
    from PIL import Image
    frames = [render(LOGO_SVG if s > 24 else small_logo(), s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
    frames[-1].save(ASSETS / "app.ico", format="ICO", sizes=[f.size for f in frames], append_images=frames[:-1])
    (ASSETS / "LOGO.svg").write_text(LOGO_SVG, encoding="utf-8")
    print("đã tạo", len(ICONS), "icon +", "logo")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "package/icons")
