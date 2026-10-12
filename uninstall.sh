#!/usr/bin/env bash
# Gỡ cài đặt OCR tool trên Linux.
#   bash uninstall.sh        hỏi từng bước
#   bash uninstall.sh -y     gỡ app + dữ liệu không hỏi (không xoá thư mục dự án, không gỡ gói hệ thống)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
YES=0; [ "${1:-}" = "-y" ] && YES=1

ask() {  # ask "câu hỏi" [mặc định y|n]
  [ "$YES" = 1 ] && return 0
  local def="${2:-y}" a
  read -r -p "$1 [$( [ "$def" = y ] && echo Y/n || echo y/N )] " a
  a="${a:-$def}"; [[ "$a" =~ ^[Yy] ]]
}
rm_path() { [ -e "$1" ] && { rm -rf -- "$1" && echo "  đã xoá $1"; } || true; }

echo "==== Gỡ OCR tool ===="
echo "Thư mục dự án: $ROOT"
ask "Tiếp tục gỡ cài đặt?" || { echo "Đã huỷ."; exit 0; }

echo "[1/5] Tắt app khay đang chạy"
pkill -f "$ROOT/.venv/bin/python" 2>/dev/null && echo "  đã tắt" || echo "  không có tiến trình nào"

echo "[2/5] Bỏ tự khởi động cùng máy"
rm_path "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/ocrtool.desktop"

echo "[3/5] Xoá môi trường Python và dữ liệu ngôn ngữ trong thư mục dự án"
rm_path "$ROOT/.venv"
rm_path "$ROOT/tessdata"
rm_path "$ROOT/src/ocrtool.egg-info"
find "$ROOT" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "[4/5] Dữ liệu người dùng (cấu hình, lịch sử ảnh+chữ, log)"
DATA="${XDG_STATE_HOME:-$HOME/.local/state}/ocrtool"
if [ -e "$DATA" ]; then
  ask "Xoá $DATA ?" && rm_path "$DATA" || echo "  giữ lại"
else
  echo "  không có"
fi

echo "[5/5] Thư mục dự án"
if [ "$YES" = 0 ] && ask "Xoá luôn cả thư mục $ROOT (gồm mã nguồn)?" n; then
  cd / && rm -rf -- "$ROOT" && echo "  đã xoá $ROOT"
else
  echo "  giữ lại"
fi

echo
echo "Xong. Tesseract và gói hệ thống (python3-tk, xclip...) được giữ nguyên vì có thể app khác dùng."
echo "Muốn gỡ Tesseract: sudo apt remove tesseract-ocr   (hoặc dnf/pacman tương ứng)"
