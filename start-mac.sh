#!/bin/bash
# Agent Guard — Mac 本地一键启动脚本
# 用法： ./start-mac.sh
# 说明：未在 macOS 上实测，按脚本逻辑编写；如遇问题请查看输出的报错信息。
set -e
cd "$(dirname "$0")"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PID_FILE=".agent-guard.pids"

echo "== Agent Guard V2 启动 =="

# .env（可选）：LLM_BASE_URL / LLM_MODEL / LLM_API_KEY / GUARD_APPROVAL_TIMEOUT
if [ -f .env ]; then
  echo "-- 加载 .env --"
  set -a; . ./.env; set +a
fi
if [ -z "${LLM_API_KEY:-}" ]; then
  echo "   提示：未配置 LLM_API_KEY，将仅提供「演示 Agent」模式；"
  echo "   如需真实 LLM，自行把 key 填入 .env（已 gitignore，不会提交）后再重启。"
else
  echo "   已检测到 LLM_API_KEY，真实 LLM 模式可用。"
fi

command -v python3 >/dev/null || { echo "缺 python3，请先安装 Python 3.10+"; exit 1; }
command -v node >/dev/null || { echo "缺 node，请先安装 Node.js 18+"; exit 1; }
command -v npm >/dev/null || { echo "缺 npm"; exit 1; }

# ---- 后端 ----
if [ ! -d backend/venv ]; then
  echo "-- 创建后端虚拟环境 --"
  python3 -m venv backend/venv
fi
echo "-- 安装后端依赖 --"
backend/venv/bin/pip install -q -r backend/requirements.txt

echo "-- 启动后端 (http://localhost:${BACKEND_PORT}) --"
BACKEND_PORT="$BACKEND_PORT" AGENT_GUARD_DB_PATH="$PWD/backend/data/agent_guard.db" \
  nohup backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  --app-dir backend > backend/backend.log 2>&1 &
echo $! > "$PID_FILE"

# 等后端就绪
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null || {
  echo "后端启动失败，查看 backend/backend.log"; exit 1; }

# ---- 前端 ----
if [ ! -d frontend/node_modules ]; then
  echo "-- 安装前端依赖 --"
  (cd frontend && npm install)
fi
echo "-- 启动前端 (http://localhost:${FRONTEND_PORT}) --"
nohup bash -c "cd frontend && PORT=${FRONTEND_PORT} npx vite --port ${FRONTEND_PORT} --strictPort" \
  > frontend/frontend.log 2>&1 &
echo $! >> "$PID_FILE"

sleep 3
echo ""
echo "== 启动完成 =="
echo "前端： http://localhost:${FRONTEND_PORT}"
echo "后端： http://localhost:${BACKEND_PORT}/api/health"
echo "MCP：  http://localhost:${BACKEND_PORT}/mcp/sse"
echo "停止： ./stop-mac.sh"
command -v open >/dev/null && open "http://localhost:${FRONTEND_PORT}" || true
