@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade repair
echo.
echo Repairing the local Python environment...
echo Close any other SecureTrade windows first.
echo.
call "%~dp0repair-venv.bat"
if errorlevel 1 (
  echo Repair failed.
  pause
  exit /b 1
)
echo.
echo Repair finished. Double-click start.bat to launch.
pause
