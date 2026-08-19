@echo off
setlocal
cd /d "%~dp0"
if not exist branding mkdir branding
echo.
echo  Put your CyberSym logo in this folder as:
echo    branding\cybersym-logo.png
echo.
echo  Then refresh the SecureTrade page in the browser.
echo  If the old picture is stuck, press Ctrl+F5.
echo.
start "" explorer "%cd%\branding"
pause
