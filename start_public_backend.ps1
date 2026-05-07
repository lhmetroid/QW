param(
    [int]$Port = 0,
    [switch]$Reload,
    [switch]$KillPortOwner
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Root ".env"
$LogsDir = Join-Path $Root "logs"
$BackendScript = Join-Path $Root "start_backend.ps1"
$BackendPidFile = Join-Path $LogsDir "public_backend.pid"
$TunnelPidFile = Join-Path $LogsDir "cloudflared.pid"
$RuntimeInfoFile = Join-Path $LogsDir "public_runtime.json"
$BackendOutLog = Join-Path $LogsDir "public_backend.out.log"
$BackendErrLog = Join-Path $LogsDir "public_backend.err.log"
$ConsoleLogFile = Join-Path $LogsDir "start_public_backend.console.log"

function Get-ListeningPidByPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    $listener = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        return [int]$listener.OwningProcess
    }
    return $null
}

function Write-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    Write-Host $line
    Add-Content -LiteralPath $ConsoleLogFile -Value $line -Encoding utf8
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Default = ""
    )

    if (-not (Test-Path -LiteralPath $EnvFile)) {
        return $Default
    }

    $line = Get-Content -LiteralPath $EnvFile -Encoding utf8 -ErrorAction SilentlyContinue |
        Where-Object { $_ -match "^\s*$([Regex]::Escape($Name))\s*=" } |
        Select-Object -First 1
    if (-not $line) {
        return $Default
    }
    return (($line -split "=", 2)[1]).Trim()
}

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $Root $PathValue
}

function Stop-TrackedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidFile
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return
    }

    $pidText = (Get-Content -LiteralPath $PidFile -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if (-not $pidText) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    try {
        $proc = Get-Process -Id ([int]$pidText) -ErrorAction Stop
        Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        Write-Step "Stopped tracked process PID=$pidText"
    }
    catch {
        Write-Step "Tracked process PID=$pidText is not running"
    }
    finally {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Reset-LogFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    try {
        Set-Content -LiteralPath $Path -Value "" -Encoding utf8 -ErrorAction Stop
        return
    }
    catch {
        Write-Step "Log file busy, keep appending: $Path"
    }
}

function Show-LogTail {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [string]$Title = "",
        [int]$Tail = 40
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    if ($Title) {
        Write-Step $Title
    }

    Get-Content -LiteralPath $Path -Encoding utf8 -Tail $Tail -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host $_
        Add-Content -LiteralPath $ConsoleLogFile -Value $_ -Encoding utf8
    }
}

function Show-NewLogLines {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [ref]$Offset
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $lines = @(Get-Content -LiteralPath $Path -Encoding utf8 -ErrorAction SilentlyContinue)
    if ($lines.Count -le $Offset.Value) {
        return
    }

    for ($i = $Offset.Value; $i -lt $lines.Count; $i++) {
        Write-Host $lines[$i]
        Add-Content -LiteralPath $ConsoleLogFile -Value $lines[$i] -Encoding utf8
    }
    $Offset.Value = $lines.Count
}

function Invoke-HttpStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [switch]$SkipCertificateCheck
    )

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        $args = @("--silent", "--output", "NUL", "--write-out", "%{http_code}", "--max-time", "8")
        if ($SkipCertificateCheck) {
            $args += "--insecure"
        }
        else {
            $args += "--ssl-no-revoke"
        }
        $args += $Url
        try {
            $result = & $curl.Source @args
            if ($LASTEXITCODE -eq 0 -and $result -match '^\d+$') {
                return [int]$result
            }
        }
        catch {
        }
        return $null
    }

    try {
        if ($SkipCertificateCheck) {
            Add-Type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint srvPoint, X509Certificate certificate, WebRequest request, int certificateProblem) {
        return true;
    }
}
"@ -ErrorAction SilentlyContinue
            [System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
        }
        $response = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 8 -UseBasicParsing
        return [int]$response.StatusCode
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode) {
            return [int]$statusCode
        }
        return $null
    }
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 60,
        [switch]$SkipCertificateCheck,
        [string]$Label = "",
        [string]$ProgressMessage = "",
        [string]$LogPath = ""
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $logOffset = 0

    while ((Get-Date) -lt $deadline) {
        $statusCode = Invoke-HttpStatus -Url $Url -SkipCertificateCheck:$SkipCertificateCheck
        if ($statusCode -and $statusCode -ge 200 -and $statusCode -lt 500) {
            if ($Label) {
                Write-Step "$Label ready: HTTP $statusCode <- $Url"
            }
            return $true
        }

        if ($LogPath) {
            Show-NewLogLines -Path $LogPath -Offset ([ref]$logOffset)
        }

        $remaining = [int][Math]::Ceiling(($deadline - (Get-Date)).TotalSeconds)
        $message = if ($ProgressMessage) { $ProgressMessage } else { "Waiting for $Url" }
        Write-Step "$message; remaining=${remaining}s"
        Start-Sleep -Seconds 2
    }

    if ($Label) {
        Write-Step "$Label not ready before timeout: $Url"
    }
    return $false
}

function Wait-BackendReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int]$TargetPort,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$LauncherProcess,
        [int]$PreviousListenerPid = 0,
        [int]$TimeoutSeconds = 90,
        [switch]$SkipCertificateCheck,
        [string]$LogPath = ""
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $logOffset = 0

    while ((Get-Date) -lt $deadline) {
        $LauncherProcess.Refresh()
        $listenerPid = Get-ListeningPidByPort -TargetPort $TargetPort
        $statusCode = Invoke-HttpStatus -Url $Url -SkipCertificateCheck:$SkipCertificateCheck
        $hasNewListener = $listenerPid -and ($PreviousListenerPid -le 0 -or $listenerPid -ne $PreviousListenerPid)

        if ($statusCode -and $statusCode -ge 200 -and $statusCode -lt 500 -and $hasNewListener) {
            Write-Step "Backend ready: HTTP $statusCode <- $Url"
            return [int]$listenerPid
        }

        if ($LogPath) {
            Show-NewLogLines -Path $LogPath -Offset ([ref]$logOffset)
        }

        if ($LauncherProcess.HasExited -and -not $hasNewListener) {
            break
        }

        $remaining = [int][Math]::Ceiling(($deadline - (Get-Date)).TotalSeconds)
        if ($listenerPid -and $PreviousListenerPid -gt 0 -and $listenerPid -eq $PreviousListenerPid) {
            Write-Step "Waiting for backend health; stale listener PID $listenerPid still owns port $TargetPort; remaining=${remaining}s"
        }
        else {
            Write-Step "Waiting for backend health; remaining=${remaining}s"
        }
        Start-Sleep -Seconds 2
    }

    return $null
}

function Fail-WithDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [string]$CloudflaredLogPath = ""
    )

    Write-Step "ERROR: $Message"
    Show-LogTail -Path $BackendOutLog -Title "Last backend stdout lines:" -Tail 80
    Show-LogTail -Path $BackendErrLog -Title "Last backend stderr lines:" -Tail 80
    if ($CloudflaredLogPath) {
        Show-LogTail -Path $CloudflaredLogPath -Title "Last cloudflared log lines:" -Tail 80
    }
    throw $Message
}

function Get-CloudflaredExecutable {
    $configured = Get-DotEnvValue -Name "CLOUDFLARED_BIN"
    if ($configured) {
        $resolved = Resolve-RepoPath $configured
        if (Test-Path -LiteralPath $resolved) {
            return $resolved
        }
        throw "CLOUDFLARED_BIN points to a missing file: $resolved"
    }

    $existing = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($existing) {
        return $existing.Source
    }

    $knownPaths = @(
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        "C:\Program Files\cloudflared\cloudflared.exe"
    )
    foreach ($knownPath in $knownPaths) {
        if (Test-Path -LiteralPath $knownPath) {
            return $knownPath
        }
    }

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "Installing cloudflared via winget"
        & $winget.Source install --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -eq 0) {
            foreach ($knownPath in $knownPaths) {
                if (Test-Path -LiteralPath $knownPath) {
                    return $knownPath
                }
            }
        }
    }

    $downloadDir = Join-Path $Root ".tools\\cloudflared"
    $downloadFile = Join-Path $downloadDir "cloudflared.exe"
    if (-not (Test-Path -LiteralPath $downloadFile)) {
        New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
        Write-Step "Downloading cloudflared to $downloadFile"
        Invoke-WebRequest `
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile $downloadFile
    }
    return $downloadFile
}

New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
Set-Content -LiteralPath $ConsoleLogFile -Value "" -Encoding utf8

Write-Step "Public startup begin"
Write-Step "Workspace: $Root"
Write-Step "Reading .env configuration"

$externalBaseUrl = Get-DotEnvValue -Name "EXTERNAL_API_BASE_URL"
$tunnelToken = Get-DotEnvValue -Name "CLOUDFLARED_TUNNEL_TOKEN"
$publicHostname = Get-DotEnvValue -Name "CLOUDFLARED_PUBLIC_HOSTNAME"
$targetUrl = Get-DotEnvValue -Name "CLOUDFLARED_TARGET_URL" -Default "https://localhost:8016"
$cloudflaredLog = Resolve-RepoPath (Get-DotEnvValue -Name "CLOUDFLARED_LOG_FILE" -Default "logs/cloudflared.log")
$tunnelProtocol = (Get-DotEnvValue -Name "CLOUDFLARED_PROTOCOL" -Default (Get-DotEnvValue -Name "TUNNEL_TRANSPORT_PROTOCOL" -Default "")).ToLowerInvariant()

if ($tunnelProtocol -and $tunnelProtocol -notin @("http2", "quic", "auto")) {
    Write-Step "Unsupported CLOUDFLARED_PROTOCOL/TUNNEL_TRANSPORT_PROTOCOL '$tunnelProtocol', fallback to cloudflared default"
    $tunnelProtocol = ""
}

if (-not $externalBaseUrl) {
    throw "EXTERNAL_API_BASE_URL is not configured in .env"
}
if (-not $tunnelToken) {
    throw "CLOUDFLARED_TUNNEL_TOKEN is not configured in .env"
}
if (-not $publicHostname) {
    throw "CLOUDFLARED_PUBLIC_HOSTNAME is not configured in .env"
}

Write-Step "External base URL: $externalBaseUrl"
Write-Step "Tunnel hostname: $publicHostname"
Write-Step "Local target URL: $targetUrl"
Write-Step "Cloudflared transport protocol: $(if ($tunnelProtocol) { $tunnelProtocol } else { 'default' })"

if ($Port -le 0) {
    try {
        $targetUri = [Uri]$targetUrl
        $Port = $targetUri.Port
    }
    catch {
        $Port = 8016
    }
}
Write-Step "Resolved backend port: $Port"

$backendHealthUrl = "$($targetUrl.TrimEnd('/'))/health"
$PowerShellExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) {
    (Get-Command pwsh).Source
}
else {
    (Get-Command powershell.exe -ErrorAction Stop).Source
}

Write-Step "Stopping previous tracked public processes"
Stop-TrackedProcess -PidFile $BackendPidFile
Stop-TrackedProcess -PidFile $TunnelPidFile
Start-Sleep -Milliseconds 800

$preexistingBackendPid = Get-ListeningPidByPort -TargetPort $Port
if ($preexistingBackendPid) {
    Write-Step "Existing listener detected before startup: PID $preexistingBackendPid on port $Port"
}

Write-Step "Preparing log files"
Reset-LogFile -Path $BackendOutLog
Reset-LogFile -Path $BackendErrLog
Reset-LogFile -Path $cloudflaredLog
if (Test-Path -LiteralPath $RuntimeInfoFile) {
    Remove-Item -LiteralPath $RuntimeInfoFile -Force -ErrorAction SilentlyContinue
}

$backendArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $BackendScript,
    "-Port",
    "$Port",
    "-EnableHttps"
)
if ($Reload) {
    $backendArgs += "-Reload"
}
if ($KillPortOwner) {
    $backendArgs += "-KillPortOwner"
}

Write-Step "Starting backend script"
Write-Step "Backend stdout log: $BackendOutLog"
Write-Step "Backend stderr log: $BackendErrLog"
$backendProcess = Start-Process `
    -FilePath $PowerShellExe `
    -ArgumentList $backendArgs `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $BackendOutLog `
    -RedirectStandardError $BackendErrLog `
    -PassThru

Set-Content -LiteralPath $BackendPidFile -Value $backendProcess.Id -Encoding ascii
Write-Step "Backend launcher PID: $($backendProcess.Id)"

$backendRuntimePid = Wait-BackendReady `
    -Url $backendHealthUrl `
    -TargetPort $Port `
    -LauncherProcess $backendProcess `
    -PreviousListenerPid $preexistingBackendPid `
    -TimeoutSeconds 90 `
    -SkipCertificateCheck `
    -LogPath $BackendOutLog
if (-not $backendRuntimePid) {
    Fail-WithDiagnostics -Message "Backend did not become ready at $backendHealthUrl"
}
if ($backendRuntimePid) {
    Set-Content -LiteralPath $BackendPidFile -Value $backendRuntimePid -Encoding ascii
    Write-Step "Backend runtime PID: $backendRuntimePid"
}
else {
    Write-Step "Backend runtime PID not found on port $Port; keep launcher PID"
}

Write-Step "Locating cloudflared executable"
$cloudflaredExe = Get-CloudflaredExecutable
Write-Step "cloudflared executable: $cloudflaredExe"
Write-Step "cloudflared log: $cloudflaredLog"

$tunnelArgs = @(
    "tunnel",
    "--logfile",
    $cloudflaredLog,
    "--loglevel",
    "info",
    "run"
)
if ($tunnelProtocol) {
    $tunnelArgs = @(
        "tunnel",
        "--protocol",
        $tunnelProtocol,
        "--logfile",
        $cloudflaredLog,
        "--loglevel",
        "info",
        "run"
    )
}

$env:TUNNEL_TOKEN = $tunnelToken
Write-Step "Starting cloudflared tunnel"
$tunnelProcess = Start-Process `
    -FilePath $cloudflaredExe `
    -ArgumentList $tunnelArgs `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $TunnelPidFile -Value $tunnelProcess.Id -Encoding ascii
Write-Step "cloudflared PID: $($tunnelProcess.Id)"

$publicHealthUrl = "$($externalBaseUrl.TrimEnd('/'))/health"
$publicReady = Wait-HttpReady -Url $publicHealthUrl -TimeoutSeconds 60 -Label "Public endpoint" -ProgressMessage "Waiting for public health" -LogPath $cloudflaredLog

$runtimeInfo = [ordered]@{
    started_at = (Get-Date).ToString("s")
    backend_launcher_pid = $backendProcess.Id
    backend_pid = if ($backendRuntimePid) { $backendRuntimePid } else { $backendProcess.Id }
    cloudflared_pid = $tunnelProcess.Id
    backend_health_url = $backendHealthUrl
    public_health_url = $publicHealthUrl
    external_api_base_url = $externalBaseUrl
    public_hostname = $publicHostname
    target_url = $targetUrl
    tunnel_protocol = $tunnelProtocol
    cloudflared_exe = $cloudflaredExe
    cloudflared_log_file = $cloudflaredLog
    public_ready = $publicReady
    endpoints = @{
        docs = "$($externalBaseUrl.TrimEnd('/'))/docs"
        openapi = "$($externalBaseUrl.TrimEnd('/'))/openapi.json"
        config_check = "$($externalBaseUrl.TrimEnd('/'))/api/system/config_check"
        public_endpoints = "$($externalBaseUrl.TrimEnd('/'))/api/system/public_endpoints"
        ai_scripts = "$($externalBaseUrl.TrimEnd('/'))/api/system/ai_scripts"
        sessions = "$($externalBaseUrl.TrimEnd('/'))/api/sessions"
        qywx_callback = "$($externalBaseUrl.TrimEnd('/'))/cb/qywx"
    }
}
$runtimeInfo | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $RuntimeInfoFile -Encoding utf8

if (-not $publicReady) {
    Fail-WithDiagnostics -Message "Public endpoint did not become ready at $publicHealthUrl" -CloudflaredLogPath $cloudflaredLog
}

Write-Step "Public startup complete"
Write-Step "Backend PID: $($runtimeInfo.backend_pid)"
Write-Step "cloudflared PID: $($tunnelProcess.Id)"
Write-Step "Public base URL: $externalBaseUrl"
Write-Step "Docs URL: $($runtimeInfo.endpoints.docs)"
Write-Step "Sessions API: $($runtimeInfo.endpoints.sessions)"
Write-Step "Full startup console log: $ConsoleLogFile"
Write-Step "Realtime log viewer: $Root\watch_public_logs.bat"
