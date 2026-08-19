@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade report

set "SRC=%cd%\data\CyberSym-SecureTrade-profit-report.csv"
if not exist "%SRC%" (
  echo No profit report found yet.
  echo Expected file:
  echo   %SRC%
  echo Leave SecureTrade running so it can write rows, then try again.
  pause
  exit /b 1
)

set "DEST=%USERPROFILE%\Desktop\CyberSym-SecureTrade-profit-report.csv"
copy /Y "%SRC%" "%DEST%" >nul
echo Copied report to:
echo   %DEST%
echo.
start "" "%DEST%"
pause
