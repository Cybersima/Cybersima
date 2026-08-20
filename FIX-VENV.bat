@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade 1.6 repair

echo.
echo  CyberSym SecureTrade 1.6
echo  This deletes only the broken .venv folder in THIS copy.
echo  Your profit report in data\ is kept.
echo  Close every other SecureTrade window first.
echo.
pause

if exist .venv (
  echo Removing .venv...
  rmdir /s /q .venv
)
if exist pyvenv.cfg del /f /q pyvenv.cfg
if exist .venv (
  echo Could not delete .venv. Close SecureTrade windows and try again.
  pause
  exit /b 1
)

set PYTHONHOME=
set PYTHONPATH=
call "%~dp0scripts\find-python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

"%BASEPY%" "%~dp0scripts\windows_launch.py" --install-only
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Repair finished. Double-click start.bat
pause
