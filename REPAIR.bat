@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.5 repair
echo.
echo Optional. start.bat 1.5 already rebuilds a broken Version 4 .venv.
echo Close any other SecureTrade windows first.
echo.
call "%~dp0repair-venv.bat"
if errorlevel 1 (
  echo Repair failed. Try FIX-VENV.bat
  pause
  exit /b 1
)
echo.
echo Repair finished. Double-click start.bat to launch.
pause
