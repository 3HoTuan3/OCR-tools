#!/usr/bin/env bash
# Chạy ocrtool bằng venv của dự án:  ./ocr.sh anh.png   |   ./ocr.sh --screen --copy
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/.venv/bin/python" -m ocrtool "$@"
