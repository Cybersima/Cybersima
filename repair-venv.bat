@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem Empty PYTHONHOME/PYTHONPATH break Windows venvs (encodings / prefix errors).
set PYTHONHOME=
set PYTHONPATH=

set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.12 3.13 3.11 3.14 3) do (
    if "!PYEXE!"=="" (
      py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
      if not errorlevel 1 (
        for /f "delims=" %%P in ('py -%%V -c "import sys; print(sys.executable)"') do set "PYEXE=%%P"
      )
    )
  )
)
if "!PYEXE!"=="" (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
    if not errorlevel 1 (
      for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)"') do set "PYEXE=%%P"
    )
  )
)

if "!PYEXE!"=="" (
  echo.
  echo Python 3.11+ was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH", then run this again.
  echo.
  exit /b 1
)

echo Using: !PYEXE!
"!PYEXE!" "%~dp0scripts\ensure_venv.py"
exit /b !ERRORLEVEL!
