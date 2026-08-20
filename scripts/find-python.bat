@echo off
rem Sets BASEPY to the full path of Python 3.11+. Do not use setlocal here.
set "BASEPY="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)"') do set "BASEPY=%%i"
  goto :have_py
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto :missing
for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)"') do set "BASEPY=%%i"

:have_py
if not defined BASEPY goto :missing
exit /b 0

:missing
echo.
echo Python 3.11+ was not found.
echo Install it from https://www.python.org/downloads/
echo Tick "Add python.exe to PATH". Python 3.14 is fine.
echo.
exit /b 1
