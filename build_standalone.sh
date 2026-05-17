#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x ".venv/bin/python" ]; then
    echo "未找到 .venv，请先运行 ./setup_remap_tool.sh"
    exit 1
fi

.venv/bin/python -m pip install -r requirements-build.txt

if ! .venv/bin/python -m pip install --only-binary=:all: -r requirements-optional.txt; then
    echo "警告：可选依赖 pygame 安装失败，本次打包将不包含手柄自动识别。"
fi

rm -rf build dist

.venv/bin/python -m PyInstaller --noconfirm --clean smb_remap_tool.spec

cp -f dist/SMBRemapStudio "$SCRIPT_DIR/SMBRemapStudio"
chmod +x "$SCRIPT_DIR/SMBRemapStudio"

echo "打包完成：$SCRIPT_DIR/SMBRemapStudio"
