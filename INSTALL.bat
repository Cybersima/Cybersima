@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade installer

echo.
echo  CyberSym SecureTrade
echo  A CyberSym product
echo.
echo  This installer needs Python 3.11 or newer.
echo  If Python is missing, get it from https://www.python.org/downloads/
echo  Tick "Add python.exe to PATH" during setup, then run this again.
echo.

set "PY=python"
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ was not found.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
)

echo Installing CyberSym SecureTrade...
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\pip.exe install -e .
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)

echo.
echo Installed. Double-click start.bat to run the demo dashboard.
echo If 8080 is already in use, SecureTrade will pick the next free port.
echo When you are ready for real Coinbase orders, read LIVE.txt then GO-LIVE.bat.
echo.
pause
