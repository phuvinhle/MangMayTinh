#!/bin/bash
if ! command -v uv &> /dev/null
then
    echo "[INFO] 'uv' could not be found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi
echo "[INFO] Starting Client via uv..."
uv run python client/main.py
