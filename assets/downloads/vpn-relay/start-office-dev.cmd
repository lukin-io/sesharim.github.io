@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0office-relay.ps1" -Environment DEV -Action Start -RunUntilStopped
set "vpnRelayExit=%ERRORLEVEL%"
echo.
echo Relay stopped. Exit code: %vpnRelayExit%
pause
exit /b %vpnRelayExit%
