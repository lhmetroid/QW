param(
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$CheckOnly,
    [switch]$KillPortOwner
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"

function Stop-PortListeners {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    $listeners = @(
        Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
            Sort-Object -Property OwningProcess -Unique
    )

    if (-not $listeners) {
        Write-Host "INFO: port $TargetPort is free."
        return
    }

    foreach ($listener in $listeners) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
        $procName = if ($proc -and $proc.Name) { $proc.Name } else { "unknown" }
        $commandLine = if ($proc -and $proc.CommandLine) { $proc.CommandLine } else { "" }

        Write-Host "INFO: stopping process on port $TargetPort (PID=$($listener.OwningProcess), Name=$procName)"
        if ($commandLine) {
            Write-Host "INFO: command line: $commandLine"
        }

        try {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
        }
        catch {
            throw "Failed to stop process $($listener.OwningProcess) on port $TargetPort. $_"
        }
    }

    Start-Sleep -Milliseconds 800

    $remaining = @(
        Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
            Sort-Object -Property OwningProcess -Unique
    )
    if ($remaining) {
        $remainingPids = ($remaining | Select-Object -ExpandProperty OwningProcess) -join ", "
        throw "Port $TargetPort is still occupied after cleanup. Remaining PID(s): $remainingPids"
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $Backend "main.py"))) {
    throw "backend/main.py not found. Please run this script from the project root."
}

$env:PYTHONDONTWRITEBYTECODE = "1"

Push-Location $Backend
try {
    if ($KillPortOwner) {
        Stop-PortListeners -TargetPort $Port
    }

    python startup_check.py
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime configuration check failed."
    }

    if ($CheckOnly) {
        return
    }

    $args = @("main:app", "--host", "0.0.0.0", "--port", "$Port")
    if ($Reload) {
        $args += "--reload"
    }
    python -m uvicorn @args
}
finally {
    Pop-Location
}
