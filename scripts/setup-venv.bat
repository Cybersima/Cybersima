@echo off
rem Create or rebuild .venv for the pinned Python. Sets RUNPY.
rem Caller must cd to the product folder. Do not use setlocal.

call "%~dp0pick-python.bat"
if errorlevel 1 exit /b 1

set "RUNPY="

"%PY%" "%~dp0venv_matches.py"
if errorlevel 1 (
  echo.
  echo This folder's .venv was built with a different Python.
  echo Rebuilding it with:
  echo   %PY%
  echo Your profit CSV in data\ is kept.
  echo.
  rmdir /s /q .venv >nul 2>nul
  if exist .venv (
    echo Could not remove .venv. Close other SecureTrade windows and try again.
    exit /b 1
  )
)

if not exist .venv (
  echo Creating .venv with that Python only...
  "%PY%" -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install -U pip
  .venv\Scripts\pip.exe install -e .
  if errorlevel 1 (
    echo venv pip failed. Installing with the pinned Python instead...
    "%PY%" -m pip install -U pip
    "%PY%" -m pip install -e .
    if errorlevel 1 exit /b 1
    set "RUNPY=%PY%"
    goto :have_runpy
  )
)

.venv\Scripts\python.exe -c "import encodings, pulsearb" >nul 2>nul
if not errorlevel 1 (
  set "RUNPY=%CD%\.venv\Scripts\python.exe"
  goto :have_runpy
)

.venv\Scripts\python.exe -c "import encodings" >nul 2>nul
if not errorlevel 1 (
  echo Installing SecureTrade into .venv...
  .venv\Scripts\python.exe -m pip install -U pip
  .venv\Scripts\pip.exe install -e .
  if errorlevel 1 exit /b 1
  set "RUNPY=%CD%\.venv\Scripts\python.exe"
  goto :have_runpy
)

echo Local .venv cannot start Python. Using the pinned install directly:
echo   %PY%
"%PY%" -m pip install -U pip
"%PY%" -m pip install -e .
if errorlevel 1 exit /b 1
set "RUNPY=%PY%"

:have_runpy
if not defined RUNPY (
  echo Could not pick a Python to launch.
  exit /b 1
)

"%RUNPY%" "%~dp0crypto_ok.py"
if errorlevel 1 (
  echo.
  echo Repairing cryptography for this Python. That is required to talk to Coinbase.
  echo.
  "%RUNPY%" -m pip install -U pip
  "%RUNPY%" -m pip install --force-reinstall "cryptography>=46" "PyJWT[crypto]>=2.10"
  if errorlevel 1 exit /b 1
  "%RUNPY%" -m pip install -e .
  "%RUNPY%" "%~dp0crypto_ok.py"
  if errorlevel 1 (
    echo Could not repair cryptography. Close other SecureTrade windows and run INSTALL.bat again.
    exit /b 1
  )
)

echo Launch interpreter: %RUNPY%
exit /b 0
