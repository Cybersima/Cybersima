@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade

rem Multiple Python installs: pin one interpreter. Do not use "py -3".
set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade
echo  A CyberSym product
echo.

call "%~dp0scripts\setup-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Starting CyberSym SecureTrade...
echo If port 8080 is already in use, the app will pick the next free port.
echo Leave this window open. Close it to stop the scanner.
echo Phone app: same Wi-Fi, open the phone address printed next, type the PIN, then Add to Home Screen. See PHONE.txt
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
echo If Export fails, open that CSV in Excel or run Open-Report.bat
echo.
"%RUNPY%" -m pulsearb --demo --host 0.0.0.0 --port 8080 --open-browser
pause
