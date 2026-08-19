@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install 3.11+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -U pip
  .venv\Scripts\pip.exe install -e .
)

echo Starting CyberSym SecureTrade with live Coinbase, Kraken, Gemini, Bitstamp, and Yahoo data (paper trading).
echo Dashboard: http://127.0.0.1:8080
start "" http://127.0.0.1:8080
.venv\Scripts\python.exe -m pulsearb --host 127.0.0.1 --port 8080
pause
