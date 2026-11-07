# Agent Guard - PowerShell 启动脚本
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    Agent Guard V2 - PowerShell 本地启动" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$backendPort = 8000
$frontendPort = 5173

if (Test-Path ".env") {
    Write-Host "[--] 加载 .env 环境变量" -ForegroundColor Gray
    Get-Content ".env" | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object {
        $name, $value = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
    }
}

if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "backend\venv")) {
    Write-Host "[--] 创建 Python 虚拟环境 backend\venv ..." -ForegroundColor Yellow
    python -m venv backend\venv
}

Write-Host "[--] 检查并更新后端依赖..." -ForegroundColor Gray
& "backend\venv\Scripts\pip.exe" install -q -r backend\requirements.txt

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "[--] 安装前端依赖..." -ForegroundColor Yellow
    Push-Location frontend
    npm install
    Pop-Location
}

Write-Host "[--] 启动后端服务 (:8000)..." -ForegroundColor Green
$backendProc = Start-Process -FilePath "backend\venv\Scripts\python.exe" `
    -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $backendPort --app-dir backend" `
    -WindowStyle Minimized -PassThru

Write-Host "[--] 启动前端控制台 (:5173)..." -ForegroundColor Green
$frontendProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c cd /d frontend && npx vite --port $frontendPort --strictPort" `
    -WindowStyle Minimized -PassThru

Start-Sleep -Seconds 3
Start-Process "http://localhost:$frontendPort"

Write-Host "`n[OK] Agent Guard 启动完成！" -ForegroundColor Green
Write-Host "前端控制台： http://localhost:$frontendPort" -ForegroundColor Cyan
Write-Host "后端 API：   http://localhost:$backendPort/api/health" -ForegroundColor Cyan
Write-Host "MCP 端点：   http://localhost:$backendPort/mcp/sse" -ForegroundColor Cyan
Write-Host "停止服务请运行: .\stop-windows.ps1`n" -ForegroundColor Gray
