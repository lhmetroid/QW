param(
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"

if (-not (Test-Path -LiteralPath (Join-Path $Backend "main.py"))) {
    throw "backend/main.py not found. Please run this script from the project root."
}

$env:PYTHONDONTWRITEBYTECODE = "1"

Push-Location $Backend
try {
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
