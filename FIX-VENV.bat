@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.5 repair

echo.
echo  CyberSym SecureTrade 1.5
echo  This deletes only the broken .venv folder in THIS copy.
echo  Your profit report in data\ is kept.
echo  Close every other SecureTrade window first.
echo.
pause

if exist .venv (
  echo Removing .venv...
  rmdir /s /q .venv
)
if exist .venv (
  echo Could not delete .venv. Close SecureTrade windows and try again.
  pause
  exit /b 1
)

call "%~dp0scripts\windows-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Repair finished. Double-click start.bat
pause
