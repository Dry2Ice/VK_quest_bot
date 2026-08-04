@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" main.py
) else (
    echo venv not found, using system python...
    python main.py
)
pause