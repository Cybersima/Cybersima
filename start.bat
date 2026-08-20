@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.6

rem Do not use python -E. On Python 3.14 that makes .venv look for encodings
rem inside this folder and crash. Clearing PYTHONHOME is enough.
set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade 1.6
echo  A CyberSym product
echo.
echo  If this window does not say 1.6, you are in an old unzip folder.
echo.

call "%~dp0scripts\find-python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo Using Python: %BASEPY%
echo If port 8080 is already in use, the app will pick the next free port.
echo Leave this window open. Close it to stop the scanner.
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
echo.
"%BASEPY%" "%~dp0scripts\windows_launch.py" --demo --host 127.0.0.1 --port 8080 --open-browser
pause
