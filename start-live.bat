@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.6 live

set PYTHONHOME=
set PYTHONPATH=

echo.
echo CyberSym SecureTrade 1.6 — live prices, paper trades.
echo For real Coinbase orders, use GO-LIVE.bat after keys\coinbase.json is in place.
echo.

call "%~dp0scripts\find-python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo Using Python: %BASEPY%
"%BASEPY%" "%~dp0scripts\windows_launch.py" --host 127.0.0.1 --port 8080 --open-browser
pause
