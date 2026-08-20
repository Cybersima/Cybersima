@echo off
setlocal
cd /d "%~dp0"

rem Only used by REPAIR.bat. Normal start.bat does not call this.
set PYTHONHOME=
set PYTHONPATH=

set "PY=python"
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ was not found.
  echo Python 3.14 is fine. Tick "Add python.exe to PATH".
  exit /b 1
)

echo Using: %PY%
%PY% "%~dp0scripts\ensure_venv.py"
exit /b %ERRORLEVEL%
