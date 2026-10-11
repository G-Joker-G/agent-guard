#!/bin/bash
# Agent Guard — 停止 start-mac.sh 启动的进程
cd "$(dirname "$0")"
PID_FILE=".agent-guard.pids"
if [ -f "$PID_FILE" ]; then
  while read -r pid; do
    kill "$pid" 2>/dev/null && echo "已停止 PID $pid" || true
  done < "$PID_FILE"
  rm -f "$PID_FILE"
else
  echo "未找到 PID 文件，尝试按端口清理…"
  lsof -ti tcp:8000  | xargs kill 2>/dev/null || true
  lsof -ti tcp:5173  | xargs kill 2>/dev/null || true
fi
echo "完成"
