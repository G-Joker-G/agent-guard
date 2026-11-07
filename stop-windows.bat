@echo off
chcp 65001 >nul
title Agent Guard Windows Stopper
cd /d "%~dp0"

echo ===================================================
echo     Agent Guard - Windows 服务清理与停止
echo ===================================================

set BACKEND_PORT=8000
set FRONTEND_PORT=5173

echo [--] 正在停止端口 %BACKEND_PORT% (后端 FastAPI) ...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1 && echo [OK] 已终止后端 PID %%a
)

echo [--] 正在停止端口 %FRONTEND_PORT% (前端 Vite) ...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1 && echo [OK] 已终止前端 PID %%a
)

echo.
echo ===================================================
echo   [OK] Agent Guard 服务已全部安全停止！
echo ===================================================
timeout /t 2 /nobreak >nul
