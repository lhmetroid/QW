$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogsDir = Join-Path $Root "logs"

$Targets = @(
    @{ Path = (Join-Path $LogsDir "start_public_backend.console.log"); Prefix = "[startup] " },
    @{ Path = (Join-Path $LogsDir "public_backend.out.log"); Prefix = "[backend-out] " },
    @{ Path = (Join-Path $LogsDir "public_backend.err.log"); Prefix = "[backend-err] " },
    @{ Path = (Join-Path $LogsDir "cloudflared.log"); Prefix = "[cloudflared] " }
)

function Print-NewLines {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Target
    )

    if (-not (Test-Path -LiteralPath $Target.Path)) {
        return
    }

    $lines = @(Get-Content -LiteralPath $Target.Path -Encoding utf8 -ErrorAction SilentlyContinue)
    if (-not $Target.ContainsKey("Offset")) {
        $Target["Offset"] = [Math]::Max(0, $lines.Count - 40)
    }

    if ($lines.Count -le $Target.Offset) {
        return
    }

    for ($i = $Target.Offset; $i -lt $lines.Count; $i++) {
        Write-Host ($Target.Prefix + $lines[$i])
    }
    $Target["Offset"] = $lines.Count
}

Write-Host "Watching runtime logs under $LogsDir"
Write-Host "Press Ctrl+C to stop."

while ($true) {
    foreach ($target in $Targets) {
        Print-NewLines -Target $target
    }
    Start-Sleep -Milliseconds 1200
}
