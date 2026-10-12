#!/bin/bash
# Agent Guard — 停止 start-mac.sh 启动的进程
cd "$(dirname "$0")"
PID_FILE=".agent-guard.pids"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
if [ -f .env ]; then
  # 轻量读取 .env 里的端口（与 start-mac.sh 同源）
  set -a; . ./.env 2>/dev/null; set +a
fi
kill_port() {
  # 兜底：PID 杀不掉的残留进程（如 vite 子进程），按端口清理
  lsof -ti "tcp:$1" 2>/dev/null | xargs kill 2>/dev/null || true
}
if [ -f "$PID_FILE" ]; then
  while read -r pid; do
    kill "$pid" 2>/dev/null && echo "已停止 PID $pid" || true
  done < "$PID_FILE"
  rm -f "$PID_FILE"
  sleep 1
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
else
  echo "未找到 PID 文件，尝试按端口清理…"
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
fi
echo "完成"
