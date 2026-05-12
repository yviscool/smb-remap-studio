#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x ".venv/bin/python" ]; then
    echo "未找到 .venv，请先运行 ./setup_remap_tool.sh"
    exit 1
fi

.venv/bin/pip install pyinstaller

rm -rf build dist smb_remap_tool.spec

.venv/bin/pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onefile \
    --name SMBRemapStudio \
    --add-data assets:assets \
    smb_remap_tool.py

cp -f dist/SMBRemapStudio "$SCRIPT_DIR/SMBRemapStudio"
chmod +x "$SCRIPT_DIR/SMBRemapStudio"

echo "打包完成：$SCRIPT_DIR/SMBRemapStudio"
