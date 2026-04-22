#!/bin/bash
# 1. Ensure system dependencies for compilation (requires sudo)
echo "[INFO] Checking system dependencies for compilation..."
sudo apt-get update && sudo apt-get install -y libevdev-dev python3-dev build-essential curl

# 2. Localize UV environment
export UV_CACHE_DIR="$(pwd)/.uv_cache"
export UV_PYTHON_INSTALL_DIR="$(pwd)/.python"
# Add current dir to PATH so we can call 'uv' directly if it's here
export PATH="$PWD:$PATH"

# 3. Download UV binary locally if not exists
if [ ! -f "./uv" ]; then
    echo "[INFO] Downloading standalone 'uv' binary..."
    # Download and extract only the 'uv' binary to the current directory
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="." sh
    # If the installer put it in a bin/ folder, move it out
    if [ -f "./bin/uv" ]; then
        mv ./bin/uv ./uv
        rm -rf ./bin
    fi
    chmod +x ./uv
fi

# 4. Run application using the local uv
echo "[INFO] Starting Client..."
cd client
../uv run --python 3.12 python main.py
cd ..

echo "[INFO] Done. You can delete this folder to remove all local environments and cache."
