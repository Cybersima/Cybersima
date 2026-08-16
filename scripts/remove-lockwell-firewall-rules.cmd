@echo off
setlocal
echo Removing Lockwell Windows Firewall rules...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetFirewallRule -DisplayName 'Lockwell Block*' | Remove-NetFirewallRule; Write-Host 'Done.'"
pause
