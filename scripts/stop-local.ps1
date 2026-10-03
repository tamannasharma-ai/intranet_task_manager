$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot ".runtime"
$pidFile = Join-Path $runtimeDirectory "uvicorn.pid"

if (Test-Path $pidFile) {
    $backendPid = [int](Get-Content $pidFile)
    $backend = Get-Process -Id $backendPid -ErrorAction SilentlyContinue
    if ($backend) {
        Stop-Process -Id $backendPid
        Write-Host "Stopped FastAPI process $backendPid."
    }
    Remove-Item $pidFile -Force
}

$nginx = $env:NGINX_EXE
if (-not $nginx) {
    $nginxCandidates = @(
        (Join-Path $projectRoot "nginx\nginx.exe"),
        "C:\nginx\nginx.exe",
        "C:\nginx-1.30.4\nginx.exe",
        "C:\Program Files\nginx\nginx.exe"
    )
    $nginx = $nginxCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if ($nginx) {
    & $nginx -p $projectRoot -c (Join-Path $projectRoot "deploy\nginx.local.conf") -s stop
    Write-Host "Stopped Nginx."
}
