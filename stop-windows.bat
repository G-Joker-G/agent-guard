@echo off
setlocal
cd /d "%~dp0"
title Agent Guard Stopper

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-windows.ps1"
