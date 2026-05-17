#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "未找到可用的 Python，请先安装 Python 3。"
    exit 1
fi

if [ ! -d ".venv" ]; then
    "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if ! .venv/bin/python -m pip install --only-binary=:all: -r requirements-optional.txt; then
    echo "警告：可选依赖 pygame 安装失败，手柄自动识别会不可用。"
    echo "这不影响读取、编辑和保存 buttonmap.cfg。"
fi

echo "依赖安装完成。"
echo "运行方式：./run_remap_tool.sh"
