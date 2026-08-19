@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade live

echo Starting CyberSym SecureTrade with live Coinbase, Kraken, Gemini, Bitstamp, and Yahoo data (paper trading).
echo This is LIVE PRICES with PAPER trades. For real Coinbase orders, use GO-LIVE.bat after keys\coinbase.json is in place.
echo If port 8080 is already in use, the app will pick the next free port.
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
echo If Export fails, open that CSV in Excel or run Open-Report.bat
echo.

call "%~dp0repair-venv.bat"
if errorlevel 1 (
  echo Run REPAIR.bat first.
  pause
  exit /b 1
)

.venv\Scripts\python.exe -m pulsearb --host 127.0.0.1 --port 8080 --open-browser
pause
