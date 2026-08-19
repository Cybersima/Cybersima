@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade installer

echo.
echo  CyberSym SecureTrade
echo  A CyberSym product
echo.
echo  This installer needs Python 3.12 (3.11+ is OK). Python 3.14 often breaks Windows.
echo  Get it from https://www.python.org/downloads/
echo  Tick "Add python.exe to PATH" during setup, then run this again.
echo.

call "%~dp0repair-venv.bat"
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)

echo.
echo Installed. Double-click start.bat to run the demo dashboard.
echo If 8080 is already in use, SecureTrade will pick the next free port.
echo When you are ready for real Coinbase orders, read LIVE.txt then GO-LIVE.bat.
echo.
pause
