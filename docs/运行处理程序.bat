@echo off
setlocal
echo ==========================================
echo WeChat Chat Record Processor
echo ==========================================

:: Check if python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Starting data processing (Step 1: Extraction)...
python "d:\items\QW\docs\process_qw_chat.py"

if %errorlevel% equ 0 (
    echo Step 1 completed. Starting Step 2: Refinement and Cleaning...
    python "d:\items\QW\docs\finalize_kb.py"
    
    if %errorlevel% equ 0 (
        echo.
        echo ==========================================
        echo ALL STEPS COMPLETED SUCCESSFULLY!
        echo ==========================================
        echo Final KB File: d:\items\QW\docs\企微知识库_final.csv
        echo Raw Processed: d:\items\QW\docs\企微提取内容_processed.csv
        echo Log file: d:\items\QW\docs\process_log.txt
    ) else (
        echo Error occurred during refinement step.
    )
) else (
    echo.
    echo Error occurred during processing.
    echo Please check d:\items\QW\docs\process_log.txt for details.
)

pause
