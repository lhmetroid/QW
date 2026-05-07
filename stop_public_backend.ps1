$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Root ".env"
$LogsDir = Join-Path $Root "logs"
$PidFiles = @(
    (Join-Path $LogsDir "cloudflared.pid"),
    (Join-Path $LogsDir "public_backend.pid")
)

function Stop-PortListeners {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    function Get-DescendantProcessIds {
        param(
            [Parameter(Mandatory = $true)]
            [int]$ParentPid
        )

        $all = New-Object System.Collections.Generic.List[int]
        $queue = New-Object System.Collections.Generic.Queue[int]
        $queue.Enqueue($ParentPid)

        while ($queue.Count -gt 0) {
            $current = $queue.Dequeue()
            $children = @(
                Get-CimInstance Win32_Process -Filter "ParentProcessId = $current" -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty ProcessId
            )
            foreach ($child in $children) {
                if (-not $all.Contains([int]$child)) {
                    $all.Add([int]$child)
                    $queue.Enqueue([int]$child)
                }
            }
        }

        return @($all)
    }

    $listeners = @(
        Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
            Sort-Object -Property OwningProcess -Unique
    )

    foreach ($listener in $listeners) {
        try {
            foreach ($childPid in @(Get-DescendantProcessIds -ParentPid $listener.OwningProcess)) {
                Stop-Process -Id $childPid -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "INFO: stopped listener PID $($listener.OwningProcess) on port $TargetPort"
        }
        catch {
        }
    }
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

$targetUrl = Get-DotEnvValue -Name "CLOUDFLARED_TARGET_URL" -Default "https://localhost:8016"
$targetPort = 8016
try {
    $targetPort = ([Uri]$targetUrl).Port
}
catch {
    $targetPort = 8016
}

foreach ($pidFile in $PidFiles) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        continue
    }

    $pidRaw = Get-Content -LiteralPath $pidFile -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -First 1
    $pidText = if ($null -ne $pidRaw) { "$pidRaw".Trim() } else { "" }
    if (-not $pidText) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        continue
    }

    try {
        Stop-Process -Id ([int]$pidText) -Force -ErrorAction Stop
        Write-Host "INFO: stopped process $pidText"
    }
    catch {
        Write-Host "INFO: process $pidText not running"
    }
    finally {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "python.exe" -and
        ($_.CommandLine -like "*run_server.py*" -or $_.CommandLine -like "*-m uvicorn*" -or $_.CommandLine -like "*uvicorn main:app*") -and
        ($_.CommandLine -like "*--port $targetPort*" -or $_.CommandLine -like "*--port 8000*")
    } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            Write-Host "INFO: stopped backend python process $($_.ProcessId) on port $targetPort"
        }
        catch {
        }
    }

Stop-PortListeners -TargetPort $targetPort

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "cloudflared.exe" } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            Write-Host "INFO: stopped cloudflared process $($_.ProcessId)"
        }
        catch {
        }
    }
