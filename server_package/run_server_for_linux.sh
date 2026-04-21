#!/bin/bash
# 1. Ensure system dependencies for compilation (requires sudo)
echo "[INFO] Checking system dependencies for compilation..."
sudo apt-get update && sudo apt-get install -y libevdev-dev python3-dev build-essential curl

# 2. Localize UV environment
export UV_CACHE_DIR="./.uv_cache"
export UV_PYTHON_INSTALL_DIR="./.python"

# 3. Download UV binary locally if not exists
if [ ! -f "./uv" ]; then
    echo "[INFO] Downloading standalone 'uv' binary..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="." sh
    if [ -f "./bin/uv" ]; then
        mv ./bin/uv ./uv
        rm -rf ./bin
    fi
    chmod +x ./uv
fi

# 4. Check permissions for input devices (Keylogger)
if ! groups $USER | grep -q "\binput\b"; then
    echo "[INFO] Adding user to 'input' group..."
    sudo usermod -a -G input $USER
    echo "[INFO] Starting Server with temporary group access..."
    exec sg input "./uv run --python 3.12 python server/main.py"
else
    echo "[INFO] Starting Server..."
    ./uv run --python 3.12 python server/main.py
fi
