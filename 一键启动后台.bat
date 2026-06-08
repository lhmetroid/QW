@echo off
setlocal
chcp 65001 >nul
title QW Backend 8071
cd /d "%~dp0"

echo ============================================================
echo QW backend launcher
echo Project: %CD%
echo Port: 8071
echo Time: %DATE% %TIME%
echo ============================================================
echo.
echo Starting PowerShell backend script...
echo If this window stays here, copy the last visible line to Codex.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "& { Write-Host 'PowerShell entered. Loading start_backend.ps1...'; & '%~dp0start_backend.ps1' -Port 8071 -KillPortOwner; exit $LASTEXITCODE }"

set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Backend launcher exited with code: %EXIT_CODE%
if not "%EXIT_CODE%"=="0" (
  echo Startup failed. Check backend\logs\start_backend_8071_*.out.log
)
echo.
pause
