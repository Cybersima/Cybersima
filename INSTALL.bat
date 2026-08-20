@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade installer

echo.
echo  CyberSym SecureTrade
echo  A CyberSym product
echo.
echo  This installer pins one Python so extra installs cannot mix.
echo  Default: C:\Python314\python.exe
echo  Override: python-path.txt next to this file, one line, full path.
echo.

set PYTHONHOME=
set PYTHONPATH=

call "%~dp0scripts\setup-venv.bat"
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
