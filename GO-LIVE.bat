@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade LIVE

set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade — LIVE TRADING
echo  This sends REAL market orders with your money (Coinbase or Kraken).
echo  Each tap is $1-$25 (default $5). Session budget $25.
echo  Live Auto only runs inside the time window you set on the dashboard.
echo  Cross-venue (Coinbase vs Kraken) stays PAPER.
echo  Close this window or use Kill switch to stop.
echo.
if exist "keys\coinbase.json" goto havekeys
if exist "keys\kraken.json" goto havekeys
  echo Missing keys\coinbase.json and keys\kraken.json
  echo Read LIVE.txt. Save the key file for the exchange you will use.
  echo Then run CHECK-LIVE.bat before this file.
  echo.
  pause
  exit /b 1
:havekeys

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
echo Ready check passed. Next step starts REAL orders on Coinbase or Kraken.
echo Press Ctrl+C to cancel, or
pause

set PULSEARB_DEMO_ONLY=
set PULSEARB_EXECUTION_MODE=live
set PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK

echo.
echo Starting live trading...
echo Phone app: same Wi-Fi, open the phone address printed next, type the PIN. See PHONE.txt
echo.
"%RUNPY%" -m pulsearb --live-trading --host 0.0.0.0 --port 8080 --open-browser
pause
