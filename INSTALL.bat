@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.6 installer

echo.
echo  CyberSym SecureTrade 1.6
echo  A CyberSym product
echo.
echo  This installer needs Python 3.11 or newer. Python 3.14 is fine.
echo.

set PYTHONHOME=
set PYTHONPATH=

call "%~dp0scripts\find-python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo Using Python: %BASEPY%
"%BASEPY%" "%~dp0scripts\windows_launch.py" --install-only
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)

echo.
echo Installed. Double-click start.bat to run the demo dashboard.
echo When you are ready for real Coinbase orders, read LIVE.txt then GO-LIVE.bat.
echo.
pause
