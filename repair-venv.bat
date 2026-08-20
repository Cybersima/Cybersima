@echo off
setlocal
cd /d "%~dp0"

set PYTHONHOME=
set PYTHONPATH=

call "%~dp0scripts\find-python.bat"
if errorlevel 1 exit /b 1

echo Using: %BASEPY%
"%BASEPY%" "%~dp0scripts\windows_launch.py" --install-only
exit /b %ERRORLEVEL%
