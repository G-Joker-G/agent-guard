# Agent Guard - PowerShell 停止脚本
Set-Location -Path $PSScriptRoot

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    Agent Guard - 停止本地运行端口 (8000, 5173)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

foreach ($port in @(8000, 5173)) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connections) {
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            try {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "[OK] 已停止占用端口 $port 的进程 (PID: $procId)" -ForegroundColor Green
            } catch {
                Write-Host "[--] 无法直接停止 PID: $procId" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "[--] 端口 $port 当前无服务占用" -ForegroundColor Gray
    }
}

Write-Host "`nAgent Guard 本地服务已全部停止。`n" -ForegroundColor Green
