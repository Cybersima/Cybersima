@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade LIVE

set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade — LIVE TRADING
echo  This sends REAL Coinbase market orders with your money.
echo  Each tap is $1-$25 (default $5). Session budget $25.
echo  Auto stays OFF. Every live order is a tap.
echo  Cross-venue (Coinbase vs Kraken/Gemini/Bitstamp) stays PAPER.
echo  Close this window or use Kill switch to stop.
echo.
if not exist "keys\coinbase.json" (
  echo Missing keys\coinbase.json
  echo Read LIVE.txt, then put the Coinbase API JSON in the keys folder.
  echo Then run CHECK-LIVE.bat before this file.
  echo.
  pause
  exit /b 1
)

call "%~dp0scripts\setup-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo Running live ready check...
echo.
"%RUNPY%" -m pulsearb --check-live
if errorlevel 1 (
  echo.
  echo Live ready check failed. Fix the FAILs above.
  echo Read LIVE.txt. Then run CHECK-LIVE.bat again.
  echo.
  pause
  exit /b 1
)

echo.
echo Ready check passed. Next step starts REAL Coinbase orders.
echo Press Ctrl+C to cancel, or
pause

set PULSEARB_DEMO_ONLY=
set PULSEARB_EXECUTION_MODE=live
set PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK

echo.
echo Starting live trading...
echo.
"%RUNPY%" -m pulsearb --live-trading --host 127.0.0.1 --port 8080 --open-browser
pause
