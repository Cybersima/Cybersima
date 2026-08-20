@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.5

rem Avoid the Windows "Could not find platform independent libraries <prefix>" warning.
set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade 1.5
echo  A CyberSym product
echo.
echo  If this window does not say 1.5, you are in an old unzip folder.
echo  Cursor names like v01.4 are not the product version.
echo.

call "%~dp0scripts\windows-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Starting CyberSym SecureTrade...
echo If port 8080 is already in use, the app will pick the next free port.
echo Leave this window open. Close it to stop the scanner.
echo Profit report file: %cd%\data\CyberSym-SecureTrade-profit-report.csv
echo If Export fails, open that CSV in Excel or run Open-Report.bat
echo.
.venv\Scripts\python.exe -E -m pulsearb --demo --host 127.0.0.1 --port 8080 --open-browser
pause
