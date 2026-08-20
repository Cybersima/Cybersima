@echo off
rem Sets PY to one full python.exe path. Caller must cd to the product folder.
rem Do not use setlocal — PY must remain set for start.bat / INSTALL.bat.
rem Prefer Python 3.14 at C:\Python314. Do not use "py -3" (picks a random version).

set PYTHONHOME=
set PYTHONPATH=
set "PY="

if exist "python-path.txt" (
  for /f "usebackq tokens=* delims=" %%i in ("python-path.txt") do (
    if not defined PY call :use_if_ok "%%~i"
  )
)
if defined PY goto :done

call :use_if_ok "C:\Python314\python.exe"
if defined PY goto :done
call :use_if_ok "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if defined PY goto :done
call :use_if_ok "%ProgramFiles%\Python314\python.exe"
if defined PY goto :done
call :use_if_ok "C:\Python313\python.exe"
if defined PY goto :done
call :use_if_ok "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined PY goto :done
call :use_if_ok "C:\Python312\python.exe"
if defined PY goto :done
call :use_if_ok "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY goto :done

py -3.14 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%i in ('py -3.14 -c "import sys; print(sys.executable)"') do set "PY=%%i"
)
if defined PY goto :done

for /f "delims=" %%i in ('where python 2^>nul') do (
  if not defined PY call :use_if_ok "%%i"
)
if defined PY goto :done

echo.
echo Python 3.11+ was not found.
echo This app wants C:\Python314\python.exe
echo If Python lives somewhere else, put the full path in python-path.txt
echo next to start.bat ^(one line, for example C:\Python314\python.exe^).
echo.
exit /b 1

:done
echo Using Python: %PY%
echo If that is the wrong install, put the full path in python-path.txt next to start.bat.
exit /b 0

:use_if_ok
if defined PY goto :eof
if "%~1"=="" goto :eof
if not exist "%~1" goto :eof
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%~1"
goto :eof
