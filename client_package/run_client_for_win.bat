@echo off
setlocal
cd /d %~dp0

echo [INFO] Setting up local environment...
set "UV_CACHE_DIR=.uv_cache"
set "UV_PYTHON_INSTALL_DIR=.python"

:: 1. Download UV standalone if not exists
if not exist "uv.exe" (
    echo [INFO] Downloading standalone 'uv' binary...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    copy "%USERPROFILE%\.cargo\bin\uv.exe" "uv.exe" >nul
)

:: 2. Run application
echo [INFO] Starting Client...
.\uv.exe run --python 3.12 python client/main.py

echo [INFO] Done. Delete this folder to remove all cache and environments.
pause
