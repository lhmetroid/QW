param(
    [int]$Port = 8071,
    [int]$BackendPid = 0,
    [string]$StdoutLog = "",
    [string]$StderrLog = "",
    [int]$QuietWarningSeconds = 600
)

$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogsDir = Join-Path $Root "backend\logs"
$AppLog = Join-Path $LogsDir "app.log"
$Host.UI.RawUI.WindowTitle = "QW Backend $Port logs (viewer only)"

Write-Host "============================================================"
Write-Host "QW backend log viewer"
Write-Host "Port: $Port"
if ($BackendPid -gt 0) { Write-Host "Backend PID: $BackendPid" }
Write-Host "App log: $AppLog"
if ($StdoutLog) { Write-Host "Stdout log: $StdoutLog" }
if ($StderrLog) { Write-Host "Stderr log: $StderrLog" }
Write-Host ""
Write-Host "This window is only a log viewer. Selecting or scrolling here will not freeze the backend."
Write-Host "If there are no new lines for $QuietWarningSeconds seconds, this viewer prints a quiet warning."
Write-Host "============================================================"
Write-Host ""

$paths = @()
$paths += [pscustomobject]@{ Label = "APP"; Path = $AppLog; Position = 0L; Ready = $false }
if ($StdoutLog) { $paths += [pscustomobject]@{ Label = "STDOUT"; Path = $StdoutLog; Position = 0L; Ready = $false } }
if ($StderrLog) { $paths += [pscustomobject]@{ Label = "STDERR"; Path = $StderrLog; Position = 0L; Ready = $false } }

function Show-InitialTail {
    param([string]$Label, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Write-Host "----- $Label tail: $Path -----"
    try {
        Get-Content -LiteralPath $Path -Tail 80 -Encoding UTF8 -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "[$Label] $_"
        }
    }
    catch {
        Write-Host "[$Label] failed to read initial tail: $($_.Exception.Message)"
    }
}

foreach ($item in $paths) {
    Show-InitialTail -Label $item.Label -Path $item.Path
    if (Test-Path -LiteralPath $item.Path) {
        try {
            $info = Get-Item -LiteralPath $item.Path -ErrorAction Stop
            $item.Position = [int64]$info.Length
            $item.Ready = $true
        }
        catch {}
    }
}

$lastLineAt = Get-Date
$lastQuietWarningAt = Get-Date

while ($true) {
    foreach ($item in $paths) {
        if (-not (Test-Path -LiteralPath $item.Path)) { continue }
        try {
            $info = Get-Item -LiteralPath $item.Path -ErrorAction Stop
            if (-not $item.Ready) {
                Write-Host "[$($item.Label)] log file created: $($item.Path)"
                $item.Ready = $true
                $item.Position = 0L
            }
            if ([int64]$info.Length -lt [int64]$item.Position) {
                Write-Host "[$($item.Label)] log file was truncated/rotated; restarting from beginning."
                $item.Position = 0L
            }
            if ([int64]$info.Length -gt [int64]$item.Position) {
                $stream = [System.IO.File]::Open($item.Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                try {
                    [void]$stream.Seek([int64]$item.Position, [System.IO.SeekOrigin]::Begin)
                    $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
                    $text = $reader.ReadToEnd()
                    $item.Position = [int64]$stream.Position
                }
                finally {
                    $stream.Close()
                }
                if ($text) {
                    $lines = $text -split "`r?`n"
                    foreach ($line in $lines) {
                        if ($line.Length -gt 0) {
                            Write-Host "[$($item.Label)] $line"
                            $lastLineAt = Get-Date
                        }
                    }
                }
            }
        }
        catch {
            Write-Host "[$($item.Label)] read error: $($_.Exception.Message)"
        }
    }

    if ($BackendPid -gt 0) {
        $proc = Get-Process -Id $BackendPid -ErrorAction SilentlyContinue
        if (-not $proc) {
            Write-Host "[WATCH] backend process $BackendPid is no longer running."
            Write-Host "[WATCH] Press Ctrl+C or close this window after checking the logs above."
            $BackendPid = 0
        }
    }

    $now = Get-Date
    if (($now - $lastLineAt).TotalSeconds -ge $QuietWarningSeconds -and ($now - $lastQuietWarningAt).TotalSeconds -ge $QuietWarningSeconds) {
        Write-Host "[WATCH] No new backend log lines for $QuietWarningSeconds seconds. Check health/API manually if this is unexpected."
        $lastQuietWarningAt = $now
    }

    Start-Sleep -Seconds 1
}
