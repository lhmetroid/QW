@echo off
setlocal
chcp 65001 >nul

REM Located batch for WeCom data imported between 2026-05-12 and 2026-05-13:
REM   wecom_dialog_20260512_182303_888b35
REM
REM Default mode:
REM   TO_REVIEW = move published(active) data back to review + approved
REM
REM To batch switch the same data from review + approved back to published:
REM   change the next line from TO_REVIEW to TO_ACTIVE
set "MODE=TO_REVIEW"

set "BATCH=wecom_dialog_20260512_182303_888b35"

cd /d "%~dp0"
python scratch\wecom_status_adjust.py

if errorlevel 1 (
    echo.
    echo Failed.
    exit /b 1
)

echo.
echo Done.
exit /b 0
