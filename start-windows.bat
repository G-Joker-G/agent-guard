@echo off
chcp 65001 >nul
title Agent Guard Windows Launcher
cd /d "%~dp0"

echo ===================================================
echo     Agent Guard V2 - Windows 本地一键启动
echo ===================================================

set BACKEND_PORT=8000
set FRONTEND_PORT=5173

if exist .env (
    echo [--] 加载 .env 环境变量
    for /f "usebackq tokens=1,* delims==" %%i in (`findstr /v "^#" .env ^| findstr "="`) do (
        set "%%i=%%j"
    )
)

if "%LLM_API_KEY%"=="" (
    echo [提示] 未检测到 LLM_API_KEY，将启用内置「演示 Agent」与确定性拦截测试模式。
    echo        无需外部 API 即可完整体验 4 大核心安全路径。
) else (
    echo [OK] 已加载 LLM_API_KEY，真实 LLM Agent 模式可用。
)

echo.
echo [--] 检查运行环境...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选 "Add Python to PATH"
    pause
    exit /b 1
)

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)

:: 后端虚拟环境与依赖
if not exist "backend\venv" (
    echo [--] 创建 Python 虚拟环境 backend\venv ...
    python -m venv backend\venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
)

echo [--] 检查并更新后端依赖...
backend\venv\Scripts\pip install -q -r backend\requirements.txt

:: 前端依赖
if not exist "frontend\node_modules" (
    echo [--] 安装前端依赖...
    cd frontend && npm install && cd ..
)

echo.
echo [--] 启动后端服务 (http://127.0.0.1:%BACKEND_PORT%) ...
start "Agent Guard Backend (:8000)" /min cmd /c "backend\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --app-dir backend"

echo [--] 启动前端控制台 (http://localhost:%FRONTEND_PORT%) ...
start "Agent Guard Frontend (:5173)" /min cmd /c "cd /d frontend && npx vite --port %FRONTEND_PORT% --strictPort"

echo [--] 等待服务就绪并打开浏览器...
timeout /t 4 /nobreak >nul

start http://localhost:%FRONTEND_PORT%

echo.
echo ===================================================
echo   [OK] Agent Guard 已成功启动！
echo   前端控制台：  http://localhost:%FRONTEND_PORT%
echo   后端 API 状态：http://localhost:%BACKEND_PORT%/api/health
echo   MCP 服务端点：http://localhost:%BACKEND_PORT%/mcp/sse
echo.
echo   停止服务请双击运行：stop-windows.bat
echo ===================================================
echo.
