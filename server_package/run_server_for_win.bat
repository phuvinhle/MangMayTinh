@echo off
echo [INFO] Checking for uv...
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 'uv' is not installed. 
    echo [INFO] Installing 'uv' via PowerShell...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)
echo [INFO] Starting Server via uv...
uv run python server/main.py
pause
