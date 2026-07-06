param(
    [int]$Port = 8071,
    [int]$HealthTimeoutSeconds = 45,
    [switch]$NoLogWindow
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogsDir = Join-Path $Root "backend\logs"
$StartScript = Join-Path $Root "start_backend.ps1"
$LogViewerScript = Join-Path $Root "start_backend_log_viewer.ps1"
$BackendPidFile = Join-Path $LogsDir "backend_${Port}.pid"
$ViewerPidFile = Join-Path $LogsDir "backend_${Port}_log_viewer.pid"

if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "start_backend.ps1 not found: $StartScript"
}
if (-not (Test-Path -LiteralPath $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

function Stop-PreviousLogViewer {
    if (-not (Test-Path -LiteralPath $ViewerPidFile)) {
        return
    }
    $pidText = (Get-Content -LiteralPath $ViewerPidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $viewerPid = 0
    if (-not [int]::TryParse([string]$pidText, [ref]$viewerPid)) {
        Remove-Item -LiteralPath $ViewerPidFile -Force -ErrorAction SilentlyContinue
        return
    }
    $viewer = Get-Process -Id $viewerPid -ErrorAction SilentlyContinue
    if ($viewer) {
        Write-Host "Stopping previous log viewer PID=$viewerPid ..."
        Stop-Process -Id $viewerPid -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $ViewerPidFile -Force -ErrorAction SilentlyContinue
}

Stop-PreviousLogViewer

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $LogsDir "backend_${Port}_${stamp}.stdout.log"
$stderrLog = Join-Path $LogsDir "backend_${Port}_${stamp}.stderr.log"

$psArgs = @(
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $StartScript,
    "-Port",
    "$Port",
    "-KillPortOwner",
    "-NoConsoleLog"
)

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $psArgs `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Set-Content -LiteralPath $BackendPidFile -Value ([string]$proc.Id) -Encoding ASCII

Write-Host "Backend detached process started."
Write-Host "PID: $($proc.Id)"
Write-Host "Port: $Port"
Write-Host "Stdout log: $stdoutLog"
Write-Host "Stderr log: $stderrLog"
Write-Host "App log: $(Join-Path $LogsDir 'app.log')"
Write-Host "PID file: $BackendPidFile"

if (-not $NoLogWindow -and (Test-Path -LiteralPath $LogViewerScript)) {
    $viewerArgs = @(
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $LogViewerScript,
        "-Port",
        "$Port",
        "-BackendPid",
        "$($proc.Id)",
        "-StdoutLog",
        $stdoutLog,
        "-StderrLog",
        $stderrLog
    )
    $viewerProc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList $viewerArgs `
        -WorkingDirectory $Root `
        -WindowStyle Normal `
        -PassThru
    Set-Content -LiteralPath $ViewerPidFile -Value ([string]$viewerProc.Id) -Encoding ASCII
    Write-Host "Visible log viewer opened. PID=$($viewerProc.Id). Selecting that window will not freeze the backend."
}

$healthUrl = "http://localhost:$Port/api/health/ready"
$deadline = (Get-Date).AddSeconds([Math]::Max(5, $HealthTimeoutSeconds))
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) {
        Write-Host "Backend process exited early with code $($proc.ExitCode)."
        Write-Host "Check stderr log: $stderrLog"
        exit 1
    }

    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500) {
            $ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if ($ready) {
    Write-Host "Backend health check reached: $healthUrl"
    exit 0
}

Write-Host "Backend is still starting after $HealthTimeoutSeconds seconds."
Write-Host "This can be normal if dependency checks are slow. Watch the visible log window or log files above."
exit 0
