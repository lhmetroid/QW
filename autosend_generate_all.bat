@echo off
REM =====================================================================
REM  Autosend - one-shot trigger of background generation (per staff)
REM  What it does: POST /api/v1/mail/autosend/generate once per staff.
REM    Each staff's worker picks up ALL its current planned+failed rows
REM    and drafts them one by one, so it completes whatever is pending
REM    at the moment you run this.
REM  Safe: staff already running -> already_running (no duplicate worker);
REM        staff with nothing pending -> pending:0 (no-op).
REM  Run this ON THE SERVER MACHINE (service listens on localhost:8071).
REM  Add a staff: append its id (space separated) to STAFFS below.
REM =====================================================================
setlocal EnableDelayedExpansion
set "BASE=http://localhost:8071"
set "STAFFS=0002 0017 0141 0188 1607"

echo [%date% %time%] Starting background generation per staff...
echo Target: %BASE%
echo Staffs: %STAFFS%
echo.

for %%S in (%STAFFS%) do (
  echo === staff %%S : POST /autosend/generate ===
  powershell -NoProfile -Command "try { $b = ConvertTo-Json -InputObject @{ staff_id = '%%S' } -Compress; $r = Invoke-RestMethod -Uri '%BASE%/api/v1/mail/autosend/generate' -Method Post -ContentType 'application/json' -Body $b -TimeoutSec 30; Write-Output (ConvertTo-Json -InputObject $r -Compress) } catch { Write-Output ('ERROR: ' + $_.Exception.Message) }"
  echo.
)

echo [%date% %time%] All start commands sent.
echo Check progress: autosend_generate_status.bat
endlocal
