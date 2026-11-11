@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0check-office-relays.ps1"
set "vpnRelayCheckExit=%ERRORLEVEL%"
echo.
echo Read-only checks finished. Exit code: %vpnRelayCheckExit%
pause
exit /b %vpnRelayCheckExit%
