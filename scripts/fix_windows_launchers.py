# -*- coding: utf-8 -*-
import os

ps1_start = '''# Agent Guard - PowerShell 启动脚本
# UTF-8 with BOM
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    Agent Guard V2 - Windows 本地一键启动" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$backendPort = 8000
$frontendPort = 5173

if (Test-Path ".env") {
    Write-Host "[--] 加载 .env 环境变量..." -ForegroundColor Gray
    Get-Content ".env" | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object {
        $name, $value = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
    }
}

if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 Add Python to PATH。" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未检测到 Node.js，请先安装 Node.js 18+。" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# 虚拟环境
$venvPython = Join-Path $PSScriptRoot "backend\\venv\\Scripts\\python.exe"
$venvPip = Join-Path $PSScriptRoot "backend\\venv\\Scripts\\pip.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[--] 正在创建 Python 虚拟环境 backend\\venv ..." -ForegroundColor Yellow
    python -m venv (Join-Path $PSScriptRoot "backend\\venv")
}

Write-Host "[--] 检查后端运行依赖..." -ForegroundColor Gray
& $venvPip install -q -r (Join-Path $PSScriptRoot "backend\\requirements.txt")

# 前端依赖
$nodeModules = Join-Path $PSScriptRoot "frontend\\node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "[--] 首次启动正在安装前端依赖 (约需几秒)..." -ForegroundColor Yellow
    Push-Location (Join-Path $PSScriptRoot "frontend")
    npm install
    Pop-Location
}

# 启动后端（独立窗口保持运行）
Write-Host "[--] 启动后端服务 (http://127.0.0.1:$backendPort)..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k title Agent Guard Backend (:8000) && `"$venvPython`" -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort --app-dir backend" `
    -WorkingDirectory $PSScriptRoot

# 启动前端（独立窗口保持运行）
Write-Host "[--] 启动前端控制台 (http://localhost:$frontendPort)..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k title Agent Guard Frontend (:5173) && npm run dev" `
    -WorkingDirectory (Join-Path $PSScriptRoot "frontend")

Write-Host "[--] 等待服务初始化就绪..." -ForegroundColor Gray
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:$backendPort/api/health" -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($res) { $ready = $true; break }
    } catch {}
}

if ($ready) {
    Write-Host "[OK] 后端健康检查就绪！" -ForegroundColor Green
} else {
    Write-Host "[提示] 后端正在拉起中..." -ForegroundColor Yellow
}

Start-Sleep -Seconds 2
Write-Host "[--] 正在打开浏览器..." -ForegroundColor Cyan
Start-Process "http://localhost:$frontendPort"

Write-Host "`n===================================================" -ForegroundColor Green
Write-Host "  [OK] Agent Guard 已成功启动！" -ForegroundColor Green
Write-Host "  • 前端控制台： http://localhost:$frontendPort" -ForegroundColor Cyan
Write-Host "  • 后端 API：   http://localhost:$backendPort/api/health" -ForegroundColor Cyan
Write-Host "  • MCP 端点：   http://localhost:$backendPort/mcp/sse" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Green
Write-Host "提示：如需停止服务，请双击运行 stop-windows.bat。`n" -ForegroundColor Gray
Start-Sleep -Seconds 3
'''

ps1_stop = '''# Agent Guard - PowerShell 停止脚本
# UTF-8 with BOM
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

Write-Host "`n[OK] Agent Guard 本地服务已全部停止。`n" -ForegroundColor Green
Start-Sleep -Seconds 2
'''

bat_start = '''@echo off
setlocal
cd /d "%~dp0"
title Agent Guard Launcher

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-windows.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher exited with error code %errorlevel%.
    pause
)
'''

bat_stop = '''@echo off
setlocal
cd /d "%~dp0"
title Agent Guard Stopper

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1"
'''

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(root_dir, 'start-windows.ps1'), 'w', encoding='utf-8-sig') as f:
    f.write(ps1_start)

with open(os.path.join(root_dir, 'stop-windows.ps1'), 'w', encoding='utf-8-sig') as f:
    f.write(ps1_stop)

with open(os.path.join(root_dir, 'start-windows.bat'), 'w', encoding='utf-8') as f:
    f.write(bat_start)

with open(os.path.join(root_dir, 'stop-windows.bat'), 'w', encoding='utf-8') as f:
    f.write(bat_stop)

print('[OK] Updated windows scripts with visible console windows and auto-browser launch!')
