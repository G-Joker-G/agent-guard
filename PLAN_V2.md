# Agent Guard V2 — 升级方案（技术负责人制定，2026-10-11）

> 在 V1 基础上升级为"可信执行与安全控制平台"原型。V1 的安全语义全部保留：
> 审批绑定 scope_hash（一次一用、30 分钟 TTL）、急停网关（blocked_by_stop 终态、仅显式恢复、每次执行前复查）、
> 审计哈希链（只宣称"可检测篡改"）、演示 Agent 与执行器/DB 写路径物理隔离（测试断言）。

## 一、架构调整：单一网关（核心重构）

V1 的网关逻辑散在 `main.py`（`_advance_task` / `execute_action`）。V2 抽出
`backend/app/gateway.py`，提供**唯一**受保护工具执行入口：

```python
propose_action(session, task_id, tool, params, origin, actor) -> Action
    # 建 proposed 动作 + 审计 action.proposed；急停期间直接 blocked_by_stop

adjudicate(session, action, *, wait_for_approval, approval_timeout) -> dict
    # 1. 急停复查  2. policy.evaluate  3. allow→executor.execute
    # 4. needs_approval→建审批单；wait_for_approval 时阻塞轮询人工决策
    #    （批准→执行；拒绝/超时/急停→返回错误） 5. deny→标记 denied + 审计
```

调用方：

| 调用方 | wait_for_approval | 说明 |
|---|---|---|
| Web REST（V1 语义） | False | advance 遇审批停下；人工在审批中心决策；/execute 显式执行 |
| MCP 工具 | True | 阻塞等人工审批（可配置超时），超时/拒绝都返回结构化错误 |
| LLM Agent 循环 | True | 同 MCP；审批在控制台完成，循环继续 |

`main.py` 改为委托 `gateway.py`，V1 的 11 个 pytest 必须全绿（语义不变）。

**模型新增**：`actions.origin`（`web`/`mcp`/`llm`/`demo`），SQLite 迁移用
`ALTER TABLE ... ADD COLUMN`（init_db 内幂等执行）。

## 二、MCP 接入（`backend/app/mcp_server.py`）

- 官方 `mcp` SDK 2.x：`MCPServer("agent-guard")`，`sse_app()` 挂载到 FastAPI：
  `app.mount("/mcp", server.sse_app())` → `/mcp/sse` + `/mcp/messages/`。
- 工具（中文 description）：
  - `crm_read(customer_id)` → allow 路径
  - `crm_update(customer_id, updates)` → 审批路径
  - `mail_send(to/customer_id, subject, body, batch)` → 审批路径
  - `crm_export_all()` → deny 路径
  - `guard_check_status(action_id)` → 轮询动作状态/审批单/结果（供客户端超时后查询）
- 工具处理器 = `asyncio.to_thread(gateway.adjudicate, ...)`：**与 Web 走同一网关**，
  外部 Agent 无法绕过。每个 MCP 调用建独立 Task（标题 `MCP: <client>`），便于审计追溯。
- 审批等待：轮询 Approval 行（1s 间隔，新 session），超时默认 300s
  （`GUARD_APPROVAL_TIMEOUT` 可配）；超时只返回错误、不自动拒绝，审批单继续有效，
  客户端可用 `guard_check_status` 后续查询；等待期间检测到急停立即返回 blocked。
- 交付：`docs/MCP.md`（接入说明）+ `examples/mcp_client_demo.py`
  （官方 SDK：discover → call allow/approve/deny → 审计验证）。

## 三、真实 LLM Agent（`backend/app/llm_agent.py`）

- `openai` 包直连 OpenAI-compatible 接口；配置：
  `LLM_BASE_URL`（默认 `https://api.siliconflow.cn/v1`）、
  `LLM_MODEL`（默认 `deepseek-ai/DeepSeek-V4-Flash`）、`LLM_API_KEY`（默认空）。
- Agent 循环（后台线程跑，事件进审计/SSE）：
  系统提示词列出 4 个工具（JSON Schema）→ `chat.completions`（tools 参数）→
  tool_calls → 每个经 `gateway.adjudicate(wait_for_approval=True)` → 结果回填
  messages → 继续，直到 finish_reason=stop 或达到最大步数（默认 12）。
- **LLM 永远拿不到执行权**：它只产出 tool_calls；放行判定全在网关；
  审批只能由控制台人工完成。提示词里不放任何授权语义。
- 无 key 时：`POST /api/tasks/{id}/run-llm` 返回 409 并提示配置；UI 保留 V1
  确定性演示模式（明确标注）。
- 开发期验证：`scripts/stub_llm_server.py` —— 本地 OpenAI-compatible 桩，
  `POST /v1/chat/completions` 按任务场景返回确定性 tool_calls
  （followup：crm.read→mail.send；export_attack：crm.read→crm.export_all），
  用于端到端验证 agent 循环（plan→call→verdict→execute）。
- 场景 B 真实性：客户 6 notes 的注入指令会作为 crm.read 结果回填给 LLM；
  展示 LLM 的**真实行为**（桩固定演示被诱导；真实 LLM 如实呈现其行为，
  无论是否被诱导，网关都必须 deny export）。

## 四、实时可视化（事件总线 + 新版控制台）

- 事件源 = 审计表（唯一真相源，天然保证"审计对应实际执行"）：
  `GET /api/events` SSE，按 `since=<audit_id>` 增量推送；LLM 推理步骤记为
  `agent.step` 审计事件一并推送；心跳 15s。
- 前端新增「实时运行」Tab（默认首页）：
  任务 → Agent 推理时间线（thought 卡片）→ 工具请求卡片
  （工具名/参数/策略 verdict 徽章+原因）→ 待审批卡片内联 批准/拒绝 →
  执行结果 → 右侧实时审计时间线；全局急停按钮常驻。
- 保留原有 Tab（任务中心/审批中心/审计日志/客户数据/发件箱/演示）。
- 运行入口：任务详情页「演示 Agent 运行」（V1 语义）与「真实 LLM 运行」
  （需 key；后台线程 + SSE 实时展示）。

## 五、测试（V1 11 项全绿 + 新增）

新增 `backend/tests/test_v2_mcp.py`、`test_v2_llm.py`：

1. MCP 工具策略 enforcement：crm_read 放行执行；mail_send 走审批
   （测试内建审批单→批准→执行）；crm_export_all 拒绝且无副作用
2. 急停经 MCP 路径：stop 后 MCP crm_read → blocked_by_stop，无执行
3. 审批等待超时：极小超时 → 返回 timeout 错误；审批单仍 pending
4. Agent 循环对桩：followup 场景 → read 执行 + mail 审批后执行 + outbox 落库；
   export_attack → export 被 deny；审计事件齐全
5. MCP 来源审计对应：origin=mcp 的动作在审计中有完整事件链

## 六、打包与文档

- `requirements.txt` += `mcp`、`openai`；`.env.example` +=
  `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`/`GUARD_APPROVAL_TIMEOUT`
- `start-mac.sh`：提示配置 `LLM_API_KEY`（可选）；README 更新 V2 架构/演示
- docs：`MCP.md`（接入说明）、`LLM.md`（真实 LLM 配置）、
  `DEMO_V2.md`（A/B/C/D 演示指南）、`ARCHITECTURE_V2.md`（架构与开发总结）
- 商业计划书 PDF 与 3 分钟视频仍本次不做

## 七、已知限制（先记下，交付时如实报告）

- 真实 LLM + 真实 key 的端到端验证留待验收时（开发期用桩验证循环）
- Docker Compose / start-mac.sh 未在目标环境实测（环境无 Docker/Mac）
- 前端无真人点击联调（构建 + 接口契约检查）

## 八、里程碑

| 里程碑 | 内容 |
|---|---|
| V2-M0 | 方案（本文件）+ 网关重构 + 事件总线 + origin 迁移 |
| V2-M1 | MCP 服务器 + 示例客户端 + docs/MCP.md + 测试 |
| V2-M2 | LLM Agent 循环 + 桩 + docs/LLM.md + 测试 |
| V2-M3 | 控制台实时可视化 |
| V2-M4 | 全量测试绿 + 打包 + 文档 + 最终报告 |
