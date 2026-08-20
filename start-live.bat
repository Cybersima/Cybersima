@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade live

set PYTHONHOME=
set PYTHONPATH=

echo.
echo CyberSym SecureTrade — live prices, paper trades.
echo For real Coinbase orders, use GO-LIVE.bat after keys\coinbase.json is in place.
echo.

call "%~dp0scripts\setup-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo Starting with live Coinbase, Kraken, Gemini, Bitstamp, and Yahoo data (paper trading).
echo If port 8080 is already in use, the app will pick the next free port.
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
"%RUNPY%" -m pulsearb --host 127.0.0.1 --port 8080 --open-browser
pause
