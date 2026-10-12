#!/usr/bin/env bash
# Cài đặt trên Linux: tạo venv .venv, cài thư viện Python, tải dữ liệu tiếng Việt cho Tesseract.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
"$PY" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

if ! command -v tesseract >/dev/null 2>&1; then
  echo
  echo "[!] Chưa có Tesseract. Cài bằng một trong các lệnh:"
  echo "      Debian/Ubuntu: sudo apt install tesseract-ocr"
  echo "      Fedora:        sudo dnf install tesseract"
  echo "      Arch:          sudo pacman -S tesseract"
fi
python scripts/get_tessdata.py
echo
echo "[i] Chọn vùng màn hình cần: sudo apt install python3-tk (X11) hoặc grim+slurp (Wayland); clipboard cần xclip hoặc wl-clipboard."
echo
python -m ocrtool || true
echo
echo "Xong. Chạy app khay:  .venv/bin/python -m ocrtool.tray"
