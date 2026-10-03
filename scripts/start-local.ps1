param(
    [switch]$Restart,
    [switch]$CheckOnly,
    [ValidateRange(5, 120)][int]$TimeoutSeconds = 30
)
$ErrorActionPreference = "Stop"
# Pick up settings saved by configure-groq even from an already-open terminal.
foreach ($setting in @('GROQ_API_KEY', 'GROQ_FREE_TIER_CONFIRMED')) {
    $savedSetting = [Environment]::GetEnvironmentVariable($setting, 'User')
    if ($savedSetting) { [Environment]::SetEnvironmentVariable($setting, $savedSetting, 'Process') }
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot "logs"
$runtimeDirectory = Join-Path $projectRoot ".runtime"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pidFile = Join-Path $runtimeDirectory "uvicorn.pid"

function Get-Listener([int]$Port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}
function Test-AppHealth([string]$Url) {
    try {
        $result = Invoke-RestMethod -Uri $Url -TimeoutSec 2 -ErrorAction Stop
        return ($result.application -eq "continuum" -and $result.status -eq "ok")
    } catch { return $false }
}
function Wait-AppHealth([string]$Url, $Process = $null) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ($Process) {
            $Process.Refresh()
            if ($Process.HasExited) { return $false }
        }
        if (Test-AppHealth $Url) { return $true }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    return $false
}
function Stop-OwnedBackend {
    # A PID alone is unsafe because Windows can reuse it for another application.
    $savedId = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$savedId)) {
        throw "Invalid backend PID file: $pidFile"
    }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $savedId"
    if ($processInfo) {
        if ($processInfo.ExecutablePath -ine $python -or
            $processInfo.CommandLine -notmatch '\buvicorn\s+app\.main:app\b' -or
            $processInfo.CommandLine -notmatch '--port\s+8000\b') {
            throw "Refusing to stop PID ${savedId}: it does not match this project's backend."
        }
        # Windows venv launchers can spawn the base Python as a child; stopping
        # only the launcher leaves Uvicorn listening with stale application code.
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $savedId" |
            Where-Object { $_.Name -ne "conhost.exe" })
        foreach ($child in $children) {
            if ($child.CommandLine -notmatch '\buvicorn\s+app\.main:app\b' -or
                $child.CommandLine -notmatch '--port\s+8000\b' -or
                -not $child.CommandLine.StartsWith(('"' + $python + '"'), [StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing restart: backend has an unrecognized child process."
            }
        }
        foreach ($child in $children) {
            Stop-Process -Id $child.ProcessId -ErrorAction Stop
            Wait-Process -Id $child.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
        }
        if (Get-Process -Id $savedId -ErrorAction SilentlyContinue) {
            Stop-Process -Id $savedId -ErrorAction Stop
        }
        Wait-Process -Id $savedId -Timeout 10 -ErrorAction SilentlyContinue
        Write-Host "Stopped the project backend."
    }
    Remove-Item -LiteralPath $pidFile -Force
}
try {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Python environment missing: $python. Restore .venv and install requirements.txt."
    }
    $nginx = $env:NGINX_EXE
    if (-not $nginx) {
        $candidates = @((Join-Path $projectRoot "nginx\nginx.exe"),
            "C:\nginx\nginx.exe", "C:\nginx-1.30.4\nginx.exe", "C:\Program Files\nginx\nginx.exe")
        $nginx = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (-not $nginx -or -not (Test-Path -LiteralPath $nginx -PathType Leaf)) {
        throw "Nginx not found. Set NGINX_EXE to the full path of nginx.exe."
    }
    New-Item -ItemType Directory -Force -Path $logDirectory, $runtimeDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot "temp") | Out-Null
    $nginxConfig = Join-Path $projectRoot "deploy\nginx.local.conf"
    $nginxArguments = '-p "{0}" -c "{1}"' -f ($projectRoot -replace '\\', '/'), ($nginxConfig -replace '\\', '/')
    $check = Start-Process -FilePath $nginx -ArgumentList "$nginxArguments -t" `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -Wait -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "nginx-check.log") `
        -RedirectStandardError (Join-Path $logDirectory "nginx-check-error.log")
    if ($check.ExitCode -ne 0) { throw "Nginx configuration failed. See logs\nginx-check-error.log." }
    if ($CheckOnly) {
        Write-Host "Python executable and Nginx configuration checks passed. No services started; database connectivity not tested."
        exit 0
    }
    if ($Restart -and (Test-Path -LiteralPath $pidFile)) { Stop-OwnedBackend }
    $listeners = @(Get-Listener 8000)
    if ($Restart -and $listeners.Count -gt 0) {
        throw "Port 8000 remains occupied. No unrelated process was stopped. Stop the old backend manually."
    }
    if ($listeners.Count -gt 0) {
        if (-not (Test-AppHealth "http://127.0.0.1:8000/api/health")) {
            throw "Port 8000 is occupied but app/database health failed. An older backend may need start-app.cmd -Restart."
        }
        Write-Host "Existing backend is healthy. Use start-app.cmd -Restart to load code changes."
    } else {
        $backend = Start-Process -FilePath $python `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDirectory "uvicorn.log") `
            -RedirectStandardError (Join-Path $logDirectory "uvicorn-error.log")
        $backend.Id | Set-Content -LiteralPath $pidFile
        if (-not (Wait-AppHealth "http://127.0.0.1:8000/api/health" $backend)) {
            throw "Backend did not become healthy. Check PostgreSQL, DATABASE_URL/credentials and logs\uvicorn-error.log. Retry with -Restart if still running."
        }
        Write-Host "Backend and database are healthy (PID $($backend.Id))."
    }
    if (@(Get-Listener 80).Count -eq 0) {
        Start-Process -FilePath $nginx -ArgumentList $nginxArguments -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
    }
    if (-not (Wait-AppHealth "http://127.0.0.1/api/health")) {
        throw "Backend is healthy but port 80 is not serving this app. Check port conflicts and logs\nginx-error.log."
    }
    Write-Host "Application is ready: http://127.0.0.1"
    exit 0
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Logs: $logDirectory"
    exit 1
}
