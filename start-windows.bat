@echo off
setlocal
cd /d "%~dp0"
title Agent Guard Launcher

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-windows.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher exited with error code %errorlevel%.
    pause
)
