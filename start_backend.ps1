param(
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$CheckOnly,
    [switch]$KillPortOwner,
    [switch]$EnableHttps,
    [switch]$EnsureDevCert,
    # v1.7.193: 控制台 stdout/stderr 兜底落盘. Python logging 已写 backend/logs/app.log,
    # 这里再加一条全量 console tee, 防止 uvicorn 启动错误 / print / 未捕获异常 / 段错误丢失.
    [switch]$NoConsoleLog,
    [string]$ConsoleLogFile = ""
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$EnvFile = Join-Path $Root ".env"

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

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $listeners = @(
            Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
                Sort-Object -Property OwningProcess -Unique
        )

        if (-not $listeners) {
            if ($attempt -eq 1) {
                Write-Host "INFO: port $TargetPort is free."
            }
            else {
                Write-Host "INFO: port $TargetPort is free after cleanup."
            }
            return
        }

        if ($attempt -gt 1) {
            Write-Host "INFO: retrying cleanup for port $TargetPort (attempt $attempt/5)."
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
                $childPids = @(Get-DescendantProcessIds -ParentPid $listener.OwningProcess)
                foreach ($childPid in $childPids) {
                    Stop-Process -Id $childPid -Force -ErrorAction SilentlyContinue
                }
                Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
            }
            catch {
                throw "Failed to stop process $($listener.OwningProcess) on port $TargetPort. $_"
            }
        }

        Start-Sleep -Milliseconds 1200
    }

    $remaining = @(
        Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
            Sort-Object -Property OwningProcess -Unique
    )
    if ($remaining) {
        $remainingPids = ($remaining | Select-Object -ExpandProperty OwningProcess) -join ", "
        throw "Port $TargetPort is still occupied after cleanup. Remaining PID(s): $remainingPids"
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

function Get-DotEnvBool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [bool]$Default = $false
    )

    $value = (Get-DotEnvValue -Name $Name).ToLowerInvariant()
    if ($value -in @("1", "true", "yes", "on")) {
        return $true
    }
    if ($value -in @("0", "false", "no", "off")) {
        return $false
    }
    return $Default
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

if (-not (Test-Path -LiteralPath (Join-Path $Backend "main.py"))) {
    throw "backend/main.py not found. Please run this script from the project root."
}

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Push-Location $Backend
try {
    $targetUrl = Get-DotEnvValue -Name "CLOUDFLARED_TARGET_URL"
    $envHttpsEnabled = Get-DotEnvBool -Name "ENABLE_LOCAL_HTTPS"
    $useHttps = $EnableHttps.IsPresent -or $envHttpsEnabled -or ($targetUrl -like "https://*")
    $certFile = Resolve-RepoPath (Get-DotEnvValue -Name "LOCAL_HTTPS_CERT_FILE" -Default "backend/certs/localhost-cert.pem")
    $keyFile = Resolve-RepoPath (Get-DotEnvValue -Name "LOCAL_HTTPS_KEY_FILE" -Default "backend/certs/localhost-key.pem")

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

    $args = @("run_server.py", "--host", "localhost", "--port", "$Port")
    if ($useHttps) {
        if ($EnsureDevCert -or -not ((Test-Path -LiteralPath $certFile) -and (Test-Path -LiteralPath $keyFile))) {
            python generate_dev_cert.py --cert-file $certFile --key-file $keyFile
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to generate local HTTPS certificate."
            }
        }
        $args += @("--ssl-certfile", $certFile, "--ssl-keyfile", $keyFile)
        Write-Host "INFO: local HTTPS enabled on port $Port."
    }
    else {
        Write-Host "INFO: local HTTP enabled on port $Port."
    }
    if ($Reload) {
        $args += "--reload"
        Write-Host "INFO: hot reload enabled on port $Port."
    }
    else {
        Write-Host "INFO: hot reload disabled. Use -Reload to enable it."
    }

    # v1.7.193: 控制台 tee 落盘. 默认开, 在 $Root\logs\start_backend_<port>_<时间戳>.out.log.
    # 关掉: -NoConsoleLog. 自定义路径: -ConsoleLogFile <path>.
    if ($NoConsoleLog) {
        python @args
    }
    else {
        $consoleLogDir = Join-Path $Root "logs"
        if (-not (Test-Path -LiteralPath $consoleLogDir)) {
            New-Item -ItemType Directory -Path $consoleLogDir -Force | Out-Null
        }
        if ([string]::IsNullOrWhiteSpace($ConsoleLogFile)) {
            $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $ConsoleLogFile = Join-Path $consoleLogDir "start_backend_${Port}_${stamp}.out.log"
        }
        Write-Host "INFO: console tee -> $ConsoleLogFile (use -NoConsoleLog to disable)"
        # 2>&1 把 stderr 合并到 stdout 再交给 Tee-Object, 这样 PowerShell 控制台与文件双写;
        # Python logging 仍独立写 backend/logs/app.log (RotatingFileHandler), 两者互不影响.
        python @args 2>&1 | Tee-Object -FilePath $ConsoleLogFile -Append
    }
}
finally {
    Pop-Location
}
