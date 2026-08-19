@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found.
  echo Install Python 3.11+ from https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
  echo Installing PulseArb...
  .venv\Scripts\python.exe -m pip install -U pip
  .venv\Scripts\pip.exe install -e .
)

echo.
echo Starting PulseArb demo on http://127.0.0.1:8080
echo Leave this window open. Close it to stop the scanner.
echo.
start "" http://127.0.0.1:8080
.venv\Scripts\python.exe -m pulsearb --demo --host 127.0.0.1 --port 8080
pause
