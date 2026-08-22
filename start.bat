@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.11+ is required. Install it from https://www.python.org/downloads/
    echo Tick "Add python.exe to PATH" during setup, then run start.bat again.
    pause
    exit /b 1
  )
  set PY=python
) else (
  set PY=py -3
)
if not exist .venv (
  echo Installing CyberSym SecureTrade 2...
  %PY% -m venv .venv
  .venv\Scripts\python -m pip install -U pip
  .venv\Scripts\pip install -e .
)
echo Starting CyberSym SecureTrade 2 on http://127.0.0.1:8000
echo Paper trading is the default. Leave this window open.
.venv\Scripts\python -m securetrade desktop --demo --host 127.0.0.1 --port 8000
pause
