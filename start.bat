@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade

echo.
echo Starting CyberSym SecureTrade...
echo If port 8080 is already in use, the app will pick the next free port.
echo Leave this window open. Close it to stop the scanner.
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
echo If Export fails, open that CSV in Excel or run Open-Report.bat
echo.

call "%~dp0repair-venv.bat"
if errorlevel 1 (
  echo.
  echo Could not start. Close other SecureTrade windows and try REPAIR.bat.
  echo Prefer Python 3.12 from python.org if you currently have 3.14.
  echo.
  pause
  exit /b 1
)

.venv\Scripts\python.exe -m pulsearb --demo --host 127.0.0.1 --port 8080 --open-browser
if errorlevel 1 (
  echo.
  echo Launch failed. Double-click REPAIR.bat, then start.bat again.
  echo.
)
pause
