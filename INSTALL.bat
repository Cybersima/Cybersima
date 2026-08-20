@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.5 installer

echo.
echo  CyberSym SecureTrade 1.5
echo  A CyberSym product
echo.
echo  This installer needs Python 3.11 or newer. Python 3.14 is fine.
echo  If Python is missing, get it from https://www.python.org/downloads/
echo  Tick "Add python.exe to PATH" during setup, then run this again.
echo.

call "%~dp0scripts\windows-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Installed. Double-click start.bat to run the demo dashboard.
echo If 8080 is already in use, SecureTrade will pick the next free port.
echo When you are ready for real Coinbase orders, read LIVE.txt then GO-LIVE.bat.
echo.
pause
