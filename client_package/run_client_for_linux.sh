#!/bin/bash
# 1. Check and install system dependencies
if [ -f /etc/debian_version ]; then
    if ! dpkg -l | grep -q libevdev-dev; then
        echo "[INFO] Installing missing system dependencies (requires sudo)..."
        sudo apt-get update && sudo apt-get install -y python3-dev libevdev-dev
    fi
fi

# 2. Check for uv
if ! command -v uv &> /dev/null
then
    echo "[INFO] Installing 'uv'..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

# 3. Check permissions and run
if ! groups $USER | grep -q "\binput\b"; then
    echo "[INFO] Adding $USER to 'input' group for pynput..."
    sudo usermod -a -G input $USER
    echo "[INFO] Running application with temporary group access..."
    # 'sg' allows running the command with the new group immediately
    exec sg input "uv run python client/main.py"
else
    echo "[INFO] Starting Client via uv..."
    uv run python client/main.py
fi
