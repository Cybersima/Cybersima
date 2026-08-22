@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CyberSym SecureTrade logo
if not exist branding mkdir branding

set "SRC=%~1"
if "%SRC%"=="" (
  echo.
  echo  Pick your CyberSym crest ^(PNG, JPG, or WebP^).
  echo  This copies it into branding\ so the dashboard can find it.
  echo.
  for /f "usebackq delims=" %%I in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Title = 'CyberSym SecureTrade — pick your logo'; $d.Filter = 'Images (*.png;*.jpg;*.jpeg;*.webp)|*.png;*.jpg;*.jpeg;*.webp|All files (*.*)|*.*'; $d.Multiselect = $false; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "SRC=%%I"
)

if "%SRC%"=="" goto :hint
if not exist "%SRC%" goto :hint

set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=%cd%\.venv\Scripts\python.exe"
if not defined PYEXE if exist "C:\Python314\python.exe" set "PYEXE=C:\Python314\python.exe"

if defined PYEXE (
  "%PYEXE%" -c "from pulsearb.branding import install_logo; import os; p=install_logo(os.environ['SRC']); print('Installed', p)"
  if errorlevel 1 goto :copy_fallback
  goto :done
)

:copy_fallback
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$src = Get-Item -LiteralPath $env:SRC;" ^
  "$ext = $src.Extension.ToLower();" ^
  "if (@('.png','.jpg','.jpeg','.webp') -notcontains $ext) { throw 'Use a PNG, JPG, or WebP image.' };" ^
  "$destDir = Join-Path (Get-Location) 'branding';" ^
  "New-Item -ItemType Directory -Force -Path $destDir | Out-Null;" ^
  "Get-ChildItem -LiteralPath $destDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(cybersym-logo|logo)\.(png|jpe?g|webp)$' } | Remove-Item -Force;" ^
  "$dest = Join-Path $destDir ('cybersym-logo' + $ext);" ^
  "Copy-Item -LiteralPath $src.FullName -Destination $dest -Force;" ^
  "Write-Host ('Installed ' + $dest)"
if errorlevel 1 (
  echo Could not copy that image.
  pause
  exit /b 1
)

:done
echo.
echo  Logo installed. In the browser press Ctrl+F5 ^(hard refresh^).
echo  You do not need to restart SecureTrade.
echo  If you still see the old crest, close extra SecureTrade windows
echo  and start again so you are on the window whose black console
echo  is this folder.
echo.
pause
exit /b 0

:hint
echo.
echo  No image selected. Put a PNG, JPG, or WebP in:
echo    %cd%\branding
echo  Name it cybersym-logo.png or just drop it in that folder.
echo  Then press Ctrl+F5 on the dashboard.
echo.
start "" explorer "%cd%\branding"
pause
exit /b 1
