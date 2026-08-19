@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade live

set PYTHONHOME=
set PYTHONPATH=

if not exist .venv (
  echo Run INSTALL.bat first.
  pause
  exit /b 1
)

echo Starting CyberSym SecureTrade with live Coinbase, Kraken, Gemini, Bitstamp, and Yahoo data (paper trading).
echo This is LIVE PRICES with PAPER trades. For real Coinbase orders, use GO-LIVE.bat after keys\coinbase.json is in place.
echo If port 8080 is already in use, the app will pick the next free port.
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
echo If Export fails, open that CSV in Excel or run Open-Report.bat
.venv\Scripts\python.exe -E -m pulsearb --host 127.0.0.1 --port 8080 --open-browser
pause
