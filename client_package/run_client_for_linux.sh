#!/bin/bash
# 1. Ensure system dependencies for compilation (requires sudo)
echo "[INFO] Checking system dependencies for compilation..."
sudo apt-get update && sudo apt-get install -y libevdev-dev python3-dev build-essential

# 2. Localize UV (Everything stays in this folder)
export UV_CACHE_DIR="./.uv_cache"
export UV_PYTHON_INSTALL_DIR="./.python"

# 3. Download UV binary locally if not exists
if [ ! -f "./uv" ]; then
    echo "[INFO] Downloading standalone 'uv' binary to this folder..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=. sh
fi

# 4. Run application using the local uv
echo "[INFO] Starting Client..."
./uv run --python 3.12 python client/main.py

echo "[INFO] Done. You can delete this folder to remove all local environments and cache."
