@echo off
setlocal
chcp 65001 >nul
title QW Backend 8071 Launcher
cd /d "%~dp0"

echo ============================================================
echo QW backend launcher
echo Project: %CD%
echo Port: 8071
echo Time: %DATE% %TIME%
echo ============================================================
echo.
echo Starting backend in detached mode with a visible log viewer...
echo The real backend process runs hidden and writes logs to files.
echo A separate visible log window will open for monitoring.
echo Selecting or scrolling the log window cannot freeze the backend.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_backend_detached.ps1" -Port 8071

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
