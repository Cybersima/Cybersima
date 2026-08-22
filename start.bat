@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo CyberSym SecureTrade 2
echo.

set "PY_EXE="
set "PY_VER="
set "PICK=%~dp0packaging\pick_python.py"
set "TAG=%TEMP%\securetrade-python.txt"

rem Official 3.14.7 lives at python.exe — never use python3.14t.exe
call :probe_file "%LocalAppData%\Programs\Python\Python314\python.exe"
if defined PY_EXE goto :have_python
call :probe_file "C:\Python314\python.exe"
if defined PY_EXE goto :have_python
call :probe_file "%ProgramFiles%\Python314\python.exe"
if defined PY_EXE goto :have_python
call :probe_file "%ProgramFiles(x86)%\Python314\python.exe"
if defined PY_EXE goto :have_python

call :probe py -3.12
if defined PY_EXE goto :have_python
call :probe py -3.13
if defined PY_EXE goto :have_python
call :probe py -3.11
if defined PY_EXE goto :have_python
call :probe py -3.14-64
if defined PY_EXE goto :have_python
call :probe py -3.14
if defined PY_EXE goto :have_python
call :probe py -3
if defined PY_EXE goto :have_python
call :probe python
if defined PY_EXE goto :have_python
call :probe python3
if defined PY_EXE goto :have_python

echo.
echo Python 3.14.7 is fine IF it is the regular python.exe.
echo SecureTrade cannot use the experimental free-threaded file
echo   C:\Python314\python3.14t.exe
echo.
echo Check which one you have:
echo   C:\Python314\python.exe -c "import sys; print(sys.executable); print(sys.version)"
echo That must print python.exe — not python3.14t.exe — and must not
echo say "free-threading".
echo.
echo Then delete the .venv folder in this directory and run start.bat again.
pause
exit /b 1

:have_python
echo Using !PY_EXE!  ^(Python !PY_VER!^)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import encodings" >nul 2>&1
  if errorlevel 1 (
    echo Removing broken .venv from the previous install attempt...
    rmdir /s /q ".venv" 2>nul
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Installing CyberSym SecureTrade 2...
  "!PY_EXE!" -m venv --clear ".venv"
  if errorlevel 1 (
    echo Failed to create .venv with !PY_EXE!
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -c "import encodings" >nul 2>&1
  if errorlevel 1 (
    echo The new .venv cannot import encodings. Deleting it.
    echo Use C:\Python314\python.exe (3.14.7), not python3.14t.exe.
    rmdir /s /q ".venv" 2>nul
    pause
    exit /b 1
  )
  echo Upgrading pip...
  ".venv\Scripts\python.exe" -m pip install -U pip
  if errorlevel 1 goto :install_fail
  echo Installing SecureTrade...
  ".venv\Scripts\python.exe" -m pip install -e "."
  if errorlevel 1 goto :install_fail
)

echo.
echo Starting command center on http://127.0.0.1:8000
echo Paper trading is the default. Leave this window open.
echo.
".venv\Scripts\python.exe" -m securetrade desktop --demo --host 127.0.0.1 --port 8000
set "ERR=!errorlevel!"
if not "!ERR!"=="0" echo SecureTrade exited with code !ERR!
pause
exit /b !ERR!

:install_fail
echo.
echo Install failed. Delete the .venv folder and run start.bat again
echo after confirming C:\Python314\python.exe works (not python3.14t.exe).
pause
exit /b 1

:probe_file
if not exist "%~1" exit /b 1
call :probe "%~1"
exit /b %errorlevel%

:probe
set "CAND=%*"
%CAND% "%PICK%" "%TAG%" >nul 2>&1
if errorlevel 1 (
  exit /b 1
)
if not exist "%TAG%" exit /b 1
set /p PY_EXE=<"%TAG%"
set "PY_VER="
for /f "skip=1 usebackq delims=" %%L in ("%TAG%") do (
  if not defined PY_VER set "PY_VER=%%L"
)
if not defined PY_EXE exit /b 1
exit /b 0
