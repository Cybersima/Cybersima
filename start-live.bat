@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade live

set PYTHONHOME=
set PYTHONPATH=

echo.
echo CyberSym SecureTrade — live prices, paper trades.
echo Practice on Paper. Switch to Live on the dashboard when you are ready.
echo GO-LIVE.bat still starts already live if you prefer.
echo.

call "%~dp0scripts\setup-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo Starting with live Coinbase, Kraken, Gemini, OANDA, and Robinhood data (paper trading).
echo If port 8080 is already in use, the app will pick the next free port.
echo Phone app: same Wi-Fi, open the phone address printed next, type the PIN, then Add to Home Screen. See PHONE.txt
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
"%RUNPY%" -m pulsearb --host 0.0.0.0 --port 8080 --open-browser
pause
