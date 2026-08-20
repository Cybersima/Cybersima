@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.6 LIVE

set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade 1.6 — LIVE TRADING
echo  This sends REAL Coinbase market orders with your money.
echo  Default cap is $25 per trade.
echo  Cross-venue (Coinbase vs Kraken/Gemini/Bitstamp) stays PAPER.
echo  Close this window or use Kill switch to stop.
echo.
if not exist "keys\coinbase.json" (
  echo Missing keys\coinbase.json
  echo Read LIVE.txt, then put the Coinbase API JSON in the keys folder.
  echo.
  pause
  exit /b 1
)

echo Press Ctrl+C to cancel, or
pause

call "%~dp0scripts\find-python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

set PULSEARB_DEMO_ONLY=
set PULSEARB_EXECUTION_MODE=live
set PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK

echo.
echo Using Python: %BASEPY%
echo Starting live trading...
echo.
"%BASEPY%" "%~dp0scripts\windows_launch.py" --live-trading --host 127.0.0.1 --port 8080 --open-browser
pause
