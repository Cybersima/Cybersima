@echo off
setlocal
cd /d "%~dp0\.."

if "%LOCKWELL_GUARD_TOKEN%"=="" (
  echo Set LOCKWELL_GUARD_TOKEN first.
  echo Example:
  echo   set LOCKWELL_GUARD_TOKEN=your-token-here
  echo   scripts\start-network-guard-enforce.cmd
  echo.
  echo Or open Network Guard in the app and copy the token.
  pause
  exit /b 2
)

if "%LOCKWELL_API%"=="" set LOCKWELL_API=http://127.0.0.1:5000

echo Starting Network Guard in ENFORCE mode.
echo This writes real Windows Firewall rules. Run this Command Prompt / script as Administrator.
echo API=%LOCKWELL_API%
echo.

cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo Python venv missing. Start Lockwell once with scripts\start.cmd first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m network_guard.agent --mode enforce --force-simulate
if errorlevel 1 (
  echo.
  echo Enforce start failed. Re-run as Administrator and confirm the token is correct.
  pause
)
