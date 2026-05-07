@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe not found. Please create a virtual environment first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
set SENSEVOICE_MOCK=0
set SENSEVOICE_DEVICE=cuda:0
python run_server.py
pause
