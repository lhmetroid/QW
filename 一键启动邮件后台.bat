@echo off
setlocal
chcp 65001 >nul
title QW Mail-only Backend 8071 Launcher
cd /d "%~dp0"

echo ============================================================
echo QW Mail-only Backend Launcher (WeChat/WeCom Polling Disabled)
echo Project: %CD%
echo Port: 8071
echo Time: %DATE% %TIME%
echo ============================================================
echo.
echo Starting mail backend in detached mode with a visible log viewer...
echo The real backend process runs hidden and writes logs to files.
echo A separate visible log window will open for monitoring.
echo WeChat-related background polling is explicitly disabled.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_mail_backend_detached.ps1" -Port 8071

set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Backend detached launcher exited with code: %EXIT_CODE%
if not "%EXIT_CODE%"=="0" (
  echo Startup failed. Check backend\logs\backend_8071_*.stderr.log
) else (
  echo Backend has been started or is still starting in background.
  echo Visible log viewer should already be open.
  echo Runtime log: backend\logs\app.log
  echo Stdout log: backend\logs\backend_8071_*.stdout.log
  echo Stderr log: backend\logs\backend_8071_*.stderr.log
)
echo.
pause
