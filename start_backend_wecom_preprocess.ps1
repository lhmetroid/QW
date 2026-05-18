param(
    [int]$Port = 8071,
    [int]$RowLimit = 100,
    [int]$TimeoutSeconds = 240,
    [string]$BatchId = "",
    [switch]$CheckOnly,
    [switch]$NoAutoPreprocess
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$PreprocessLog = Join-Path $LogDir "wecom_preprocess_$RunStamp.log"
$BackendOutLog = Join-Path $LogDir "backend_8071_$RunStamp.out.log"
$BackendErrLog = Join-Path $LogDir "backend_8071_$RunStamp.err.log"

function Write-RunLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
    Write-Host $line
    Add-Content -LiteralPath $PreprocessLog -Encoding utf8 -Value $line
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body = $null
    )

    $params = @{
        Method = $Method
        Uri = $Uri
        TimeoutSec = 30
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json; charset=utf-8"
        $params.Body = ($Body | ConvertTo-Json -Depth 8)
    }
    return Invoke-RestMethod @params
}

function Wait-BackendReady {
    param([string]$BaseUrl)
    for ($i = 1; $i -le 90; $i++) {
        try {
            $health = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/health/ready"
            if ($health) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Get-PendingCount {
    param([string]$BaseUrl, [string]$TargetBatchId)
    $encodedBatch = [uri]::EscapeDataString($TargetBatchId)
    $data = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/wecom/raw/messages?batch_id=$encodedBatch&row_status=pending&limit=1&offset=0"
    return [int]($data.total)
}

function Resolve-TargetBatch {
    param([string]$BaseUrl, [string]$PreferredBatchId)
    if (-not [string]::IsNullOrWhiteSpace($PreferredBatchId)) {
        return $PreferredBatchId
    }

    $batches = (Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/wecom/raw/batches").batches
    foreach ($batch in $batches) {
        $pending = Get-PendingCount -BaseUrl $BaseUrl -TargetBatchId $batch.batch_id
        if ($pending -gt 0) {
            return $batch.batch_id
        }
    }
    if ($batches -and $batches.Count -gt 0) {
        return $batches[0].batch_id
    }
    throw "没有找到企微数据批次。"
}

if ($CheckOnly) {
    Write-RunLog "CheckOnly: script syntax ok."
    exit 0
}

Set-Location $Root

# Local LAN LLM1 runtime override. This does not modify .env.
$env:LLM1_API_URL = "http://10.0.0.210:89/v1"
$env:LLM1_API_KEY = "app-fpp2MlVF8cpaWPaV4OA5jpWp"
$env:LLM1_MODEL = "qwen14b"
$env:LLM1_TIMEOUT_SECONDS = "100"
$env:STAGE1_USE_LLM2 = "true"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$BaseUrl = "http://localhost:$Port"
Write-RunLog "启动本地后台，端口 $Port；LLM1_API_URL=$($env:LLM1_API_URL)，LLM1_MODEL=$($env:LLM1_MODEL)。"
Write-RunLog "预处理日志：$PreprocessLog"
Write-RunLog "后台输出日志：$BackendOutLog"

$backendScript = Join-Path $Root "start_backend.ps1"
$backendArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $backendScript,
    "-Port", "$Port",
    "-KillPortOwner"
)

$backendProcess = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $backendArgs `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $BackendOutLog `
    -RedirectStandardError $BackendErrLog `
    -WindowStyle Hidden `
    -PassThru

Write-RunLog "后台进程已启动，PID=$($backendProcess.Id)，等待健康检查..."
if (-not (Wait-BackendReady -BaseUrl $BaseUrl)) {
    Write-RunLog "后台健康检查超时，请查看：$BackendOutLog / $BackendErrLog"
    throw "Backend readiness timeout."
}
Write-RunLog "后台已就绪：$BaseUrl"

if ($NoAutoPreprocess) {
    Write-RunLog "已按参数跳过自动预处理，后台保持运行。"
    Wait-Process -Id $backendProcess.Id
    exit 0
}

$targetBatchId = Resolve-TargetBatch -BaseUrl $BaseUrl -PreferredBatchId $BatchId
Write-RunLog "自动预处理批次：$targetBatchId；每批约 $RowLimit 行，单切片超时 $TimeoutSeconds 秒。"

while ($true) {
    $pending = Get-PendingCount -BaseUrl $BaseUrl -TargetBatchId $targetBatchId
    if ($pending -le 0) {
        Write-RunLog "待处理数据已清空，自动预处理结束。后台继续运行。"
        break
    }

    Write-RunLog "当前待处理行数：$pending。提交下一批预处理任务..."
    $startResp = Invoke-JsonRequest -Method POST -Uri "$BaseUrl/api/wecom/raw/preprocess" -Body @{
        batch_id = $targetBatchId
        row_limit = $RowLimit
        timeout_seconds = $TimeoutSeconds
    }

    if ($startResp.status -eq "done") {
        Write-RunLog "后端返回：$($startResp.message)"
        break
    }

    $jobId = $startResp.job_id
    if ([string]::IsNullOrWhiteSpace($jobId)) {
        throw "预处理任务未返回 job_id。"
    }

    $rangePrinted = $false
    $lastProgress = ""
    while ($true) {
        Start-Sleep -Seconds 5
        $job = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/wecom/raw/preprocess/status/$jobId"

        if (-not $rangePrinted -and $job.selected_rows) {
            $range = "$($job.selected_row_start)-$($job.selected_row_end)"
            Write-RunLog "本次取 $range，共 $($job.selected_rows) 行 / $($job.selected_slices) 个切片，开始预处理。"
            $rangePrinted = $true
        }

        $doneSlices = [int]($job.processed_slices) + [int]($job.failed_slices)
        $totalSlices = [int]($job.selected_slices)
        if ($totalSlices -gt 0) {
            $progress = "完成 $doneSlices/$totalSlices，成功 $($job.processed_slices)，失败 $($job.failed_slices)，当前切片 $($job.current_slice_id)"
            if ($progress -ne $lastProgress) {
                Write-RunLog $progress
                $lastProgress = $progress
            }
        }

        if ($job.status -eq "done") {
            $range = if ($job.selected_rows) { "$($job.selected_row_start)-$($job.selected_row_end)" } else { "未知范围" }
            Write-RunLog "本次取 $range，预处理完成：成功 $($job.processed_slices) 个切片，失败 $($job.failed_slices) 个切片，用时 $($job.elapsed_ms) ms。"
            break
        }
        if ($job.status -eq "error") {
            Write-RunLog "预处理任务失败：后端返回 error。详细原因请查看后台输出日志：$BackendOutLog"
            throw "Preprocess job failed. See backend log."
        }
        if ($job.status -eq "not_found") {
            throw "预处理任务不存在：$jobId"
        }
    }
}

Write-RunLog "后台仍在运行，按 Ctrl+C 可结束此窗口；如需停止后台，请关闭 PID=$($backendProcess.Id) 或运行停止脚本。"
Wait-Process -Id $backendProcess.Id
