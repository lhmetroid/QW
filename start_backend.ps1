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
            $proc = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
            $procName = if ($proc -and $proc.ProcessName) { $proc.ProcessName } else { "unknown" }

            Write-Host "INFO: stopping process on port $TargetPort (PID=$($listener.OwningProcess), Name=$procName)"

            try {
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
# v1.7.194: Tee-Object 管道下 python stdout 会从行缓冲变块缓冲(4KB), 控制台与日志文件可能延迟刷新.
# 强制无缓冲, 让 uvicorn 启动 banner / 请求日志即时出现.
$env:PYTHONUNBUFFERED = "1"

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

    # v1.7.195: 控制台 tee 落盘. 默认开, 路径用相对路径(不依赖任何机器特定的绝对路径).
    # 此刻 Push-Location $Backend 已生效, CWD = <script_dir>/backend, 所以 "logs" 即 backend/logs,
    # 与 Python logging 的 app.log 同目录, 不会再创建项目根级别的 logs/. 服务器直接拷过去就能跑.
    # 关闭 tee: -NoConsoleLog. 指定具体文件名(可绝对可相对): -ConsoleLogFile <path>.
    if ($NoConsoleLog) {
        python @args
    }
    else {
        $consoleLogDir = "logs"
        if (-not (Test-Path -LiteralPath $consoleLogDir)) {
            New-Item -ItemType Directory -Path $consoleLogDir -Force | Out-Null
        }
        if ([string]::IsNullOrWhiteSpace($ConsoleLogFile)) {
            $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $ConsoleLogFile = Join-Path $consoleLogDir "start_backend_${Port}_${stamp}.out.log"
        }
        Write-Host "INFO: console tee -> $ConsoleLogFile (relative to backend/; -NoConsoleLog to disable)"

        # v1.7.195 关键修复 (NativeCommandError 导致 uvicorn 一启动就退):
        # uvicorn 默认把 INFO 写到 stderr. 顶部 $ErrorActionPreference = "Stop" 会把 stderr 当
        # NativeCommandError 立刻终止整个脚本, 进程 (PID 7944) 启起来就被父 PowerShell 杀掉.
        # 现在做两件事:
        #   1) 临时把 EAP 降到 Continue (try/finally 还原), 让 stderr 不会中断脚本
        #   2) 用 ForEach-Object 把 stderr 派生的 ErrorRecord 对象 (会被默认格式化成
        #      "+ CategoryInfo: ... + FullyQualifiedErrorId" 红字)转回纯字符串, Tee-Object
        #      看到的就是干净文本, 既不报错也不刷屏.
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & python @args 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
                else { $_ }
            } | Tee-Object -FilePath $ConsoleLogFile -Append
        }
        finally {
            $ErrorActionPreference = $prevEAP
        }
    }
}
finally {
    Pop-Location
}
