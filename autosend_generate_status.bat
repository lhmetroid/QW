@echo off
REM =====================================================================
REM  Autosend - show per-staff generation progress (READ ONLY)
REM  Does NOT trigger generation. Shows for each staff:
REM    running / planned / drafting / drafted / failed / remaining
REM =====================================================================
setlocal EnableDelayedExpansion
set "BASE=http://localhost:8071"
set "STAFFS=0002 0017 0141 0188 1607"

echo [%date% %time%] Per-staff generation progress:
echo.
for %%S in (%STAFFS%) do (
  powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri '%BASE%/api/v1/mail/autosend/generate-status?staff_id=%%S' -TimeoutSec 20; $c = $r.counts; Write-Output ('staff %%S  running=' + $r.running + '  planned=' + (0+$c.planned) + ' drafting=' + (0+$c.drafting) + ' drafted=' + (0+$c.drafted) + ' failed=' + (0+$c.failed) + '  remaining=' + $r.remaining) } catch { Write-Output ('staff %%S  ERROR: ' + $_.Exception.Message) }"
)
echo.
endlocal
