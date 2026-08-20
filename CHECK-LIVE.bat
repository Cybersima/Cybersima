@echo off
setlocal
cd /d "%~dp0"
title CyberSym SecureTrade live check

set PYTHONHOME=
set PYTHONPATH=

echo.
echo  CyberSym SecureTrade — live ready check
echo  This does NOT send orders.
echo  It checks keys\coinbase.json and whether Coinbase will accept the key.
echo.

call "%~dp0scripts\setup-venv.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

"%RUNPY%" -m pulsearb --check-live
set CHECKERR=%ERRORLEVEL%
echo.
if not "%CHECKERR%"=="0" (
  echo Still not ready. Read the FAIL line above and LIVE.txt.
  echo Do not use GO-LIVE.bat until this check passes.
) else (
  echo Ready. On the dashboard, stay on Paper to practice, then switch to Live.
  echo Or double-click GO-LIVE.bat to start already live.
)
echo.
pause
exit /b %CHECKERR%
