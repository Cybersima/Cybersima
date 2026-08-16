@echo off
setlocal
cd /d "%~dp0\.."

REM Bypass PowerShell execution policy for this run only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo.
  echo Start failed. Make sure Python and Node.js are installed.
  pause
)
