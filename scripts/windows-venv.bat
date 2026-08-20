@echo off
rem Shared Windows venv create/repair. Call from start.bat / INSTALL.bat / FIX-VENV.bat.
rem Expects the current directory to be the product root.

set PYTHONHOME=
set PYTHONPATH=

if not defined PY set "PY=python"
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python 3.11+ was not found.
  echo Install it from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH". Python 3.14 is fine.
  echo Then run INSTALL.bat.
  echo.
  exit /b 1
)

if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -E -c "import encodings" >nul 2>nul
  if not errorlevel 1 goto :venv_ready
  echo.
  echo This folder still has the broken Version 4 Python environment.
  echo Rebuilding .venv now. Your profit CSV in data\ is kept.
  echo.
  rmdir /s /q .venv >nul 2>nul
  if exist .venv (
    echo Could not remove .venv.
    echo Close every SecureTrade window, then double-click FIX-VENV.bat
    exit /b 1
  )
)

if exist .venv\Scripts\python.exe goto :venv_ready

echo Installing CyberSym SecureTrade...
%PY% -m venv .venv
if errorlevel 1 (
  echo Failed to create .venv
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\pip.exe install -e .
if errorlevel 1 (
  echo Install failed. Try INSTALL.bat
  exit /b 1
)
goto :check_app

:venv_ready
.venv\Scripts\python.exe -E -c "import encodings" >nul 2>nul
if errorlevel 1 (
  echo Python still cannot start after checking .venv.
  echo Close other SecureTrade windows and double-click FIX-VENV.bat
  exit /b 1
)

:check_app
.venv\Scripts\python.exe -E -c "import pulsearb" >nul 2>nul
if errorlevel 1 (
  echo Installing SecureTrade packages into .venv...
  .venv\Scripts\python.exe -m pip install -U pip
  .venv\Scripts\pip.exe install -e .
  if errorlevel 1 (
    echo Install failed. Try INSTALL.bat
    exit /b 1
  )
)
exit /b 0
