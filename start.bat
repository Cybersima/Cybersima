@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade

rem Avoid the Windows "Could not find platform independent libraries <prefix>" warning.
set PYTHONHOME=
set PYTHONPATH=

set "PY=python"
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python 3.11+ was not found.
  echo Install it from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH", then run INSTALL.bat first.
  echo.
  pause
  exit /b 1
)

if not exist .venv (
  echo Installing CyberSym SecureTrade for the first time...
  %PY% -m venv .venv
  .venv\Scripts\python.exe -m pip install -U pip
  .venv\Scripts\pip.exe install -e .
  if errorlevel 1 (
    echo Install failed. Try INSTALL.bat
    pause
    exit /b 1
  )
)

echo.
echo Starting CyberSym SecureTrade...
echo If port 8080 is already in use, the app will pick the next free port.
echo Leave this window open. Close it to stop the scanner.
echo.
.venv\Scripts\python.exe -E -m pulsearb --demo --host 127.0.0.1 --port 8080 --open-browser
pause
