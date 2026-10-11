# Agent Guard MCP 接入说明

Agent Guard 通过官方 `mcp` SDK（2.x）把受保护工具暴露为 MCP 工具，
供外部 Agent（如 Claude Desktop、各类 Agent 框架）调用。
**所有 MCP 调用都经过与 Web 控制台完全相同的网关裁决路径**，外部 Agent 无法绕过。

## 端点

后端挂载：`app.mount("/mcp", build_mcp_app())`（见 `backend/app/main.py`，实现见 `backend/app/mcp_server.py`）

| 端点 | 说明 |
|---|---|
| `GET /mcp/sse` | MCP SSE 连接入口 |
| `POST /mcp/messages/` | MCP 消息通道（SDK 自动处理） |

示例：后端监听 `http://127.0.0.1:8000` 时，MCP 地址为 `http://127.0.0.1:8000/mcp/sse`。

## 工具列表与策略映射

| MCP 工具 | 网关工具 | 策略 | 行为 |
|---|---|---|---|
| `crm_read(customer_id)` | `crm.read` | allow | 只读查询，自动执行并返回客户数据 |
| `crm_update(customer_id, updates)` | `crm.update` | needs_approval | 写操作，阻塞等待人工审批 |
| `mail_send(customer_id?, to?, subject, body, batch=false)` | `mail.send` | needs_approval | 邮件进入 outbox 前必须人工审批；`batch=true` 标注高风险 |
| `crm_export_all()` | `crm.export_all` | deny | 永远拒绝，不执行、无副作用 |
| `guard_check_status(action_id)` | —（只读查询） | — | 返回动作的状态 / 策略裁决 / 审批单 / 执行结果 JSON |

## 审批流程

1. 外部 Agent 调用 `crm_update` / `mail_send` 后，网关创建动作并生成**审批单**，
   工具调用**阻塞等待**人工在 Web 控制台「审批中心」决策。
2. 等待超时默认 **300 秒**，可用环境变量 `GUARD_APPROVAL_TIMEOUT` 配置（秒）。
3. **超时不自动拒绝**：超时只返回 `approval_timeout` 错误，审批单保持 `pending`，
   人工稍后仍可在控制台批准/拒绝；客户端可用 `guard_check_status(action_id)`
   继续轮询最终状态。
4. 等待期间若触发**急停**，调用立即返回 `emergency_stop` / `blocked_by_stop`，
   不执行。
5. 批准后网关执行工具并返回真实结果；拒绝后返回 `approval_rejected`。

## 示例客户端运行步骤

```bash
# 1. 启动后端（项目根目录）
./start-mac.sh
# 或：cd backend && venv/bin/python -m uvicorn app.main:app --port 8000

# 2. 打开 Web 控制台（用于审批）：http://127.0.0.1:8000

# 3. 运行演示客户端（backend/venv 需装 mcp 包）
cd backend && venv/bin/python ../examples/mcp_client_demo.py --base http://127.0.0.1:8000
```

演示脚本会依次：发现工具 → `crm_read(1)` 自动成功 → `mail_send(...)` 提示你去
控制台审批（轮询到终态）→ `crm_export_all()` 被拒绝 → 打印本次 task 的审计事件链。

## 架构说明：外部 Agent 无法绕过网关

- MCP 工具处理器（`backend/app/mcp_server.py`）是 `async def`，内部只做一件事：
  `await asyncio.to_thread(gateway.run_protected_tool, ...)`。
- `run_protected_tool` 走**唯一**入口 `gateway.adjudicate()`：
  建任务 → `propose_action`（急停检查）→ `policy.evaluate` → allow 直接执行 /
  needs_approval 建审批单并阻塞等待 / deny 标记拒绝。
- 处理器**没有任何直达执行器（executor）的代码路径**；MCP 工具名到网关工具名
  的映射（`crm_read` → `crm.read` 等）只在处理器内部完成，不影响裁决语义。
- 每次 MCP 调用创建独立 Task（标题 `MCP 调用: <工具名>`，`origin=mcp`），
  审计表记录完整事件链（`task.created → action.proposed → action.policy →
  approval.created → approval.approved/rejected → action.executed`），
  可通过 `GET /api/audit?task_id=<id>` 追溯。
