# Agent Guard V2｜可信执行与安全控制平台（原型）

独立于 AI Agent 的**执行控制层**：Agent 可以自主思考和规划，但关键执行权限必须受到独立系统约束——**外部权限网关、人工审批、受控执行器**。

> **Agent 模式声明**：本产品支持两种 Agent 模式——
> ① **演示 Agent**（确定性模拟，非真实 LLM 推理）；
> ② **真实 LLM Agent**（OpenAI-compatible 接口，需自行配置 `LLM_API_KEY`）。
> 无论哪种 Agent，所有工具调用都经过**同一服务端网关**裁决；前端按钮状态不是安全边界。
> 所有客户数据均为虚构；邮件默认模拟发送（只写入本地发件箱），不连接任何真实系统。
> 如需真实发送，可显式开启 `REAL_MAIL_ENABLED=1` 并配置 SMTP（仅白名单地址，见下）。

## 架构

```
                    ┌─ Web 控制台（实时运行视图，SSE 事件流） ─┐
                    │  工具请求卡片 → 策略判定 → 内联审批/拒绝  │
                    │  全局急停按钮 · 实时审计时间线            │
                    └──────────────────┬──────────────────────┘
                                       │ 人工决策 / 急停
用户任务 ── Agent ──→  单一网关 gateway.py  ←── MCP 客户端（/mcp/sse 标准协议）
（演示/LLM/        propose → policy.evaluate → allow 直接执行
  MCP）            → needs_approval → 审批单 → 阻塞等待人工（可配置超时）
                   → deny → 拒绝 + 审计
                          ↓
                    受控执行器（执行前复查：急停→策略→审批绑定）
                          ↓
                    模拟 CRM / 模拟邮件 → 审计日志（哈希链，可检测篡改）
                          ↓
                    /api/events（SSE，事件源 = 审计表）
```

**安全语义**（自动化测试锁定）：
- 审批绑定 `scope_hash = sha256(tool + canonical_json(params))`：一次一用，30 分钟有效期，改参数即失效
- 急停：网关拒绝新动作、阻止未开始的动作；每次执行前复查；仅管理员显式恢复
- 演示 Agent / LLM / MCP 工具处理器**没有任何直达执行器的路径**；LLM 只产出 tool_calls，永远拿不到执行权
- 审计哈希链只宣称"可检测篡改"，不宣称防篡改

## 快速启动

### 方式一：Mac 本地脚本

```bash
./start-mac.sh   # 检查 python3/node → 建 venv 装依赖 → 启动后端 :8000 → 前端 → 自动打开浏览器
./stop-mac.sh
```

### 方式二：Docker Compose（一键启动）

```bash
docker compose up --build
# 前端 http://localhost:3000  后端 http://localhost:8000
```

### 方式三：手动启动（开发）

```bash
cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 真实 LLM 配置（可选，验收时）

```bash
cp .env.example .env   # 然后填入
# LLM_BASE_URL=https://api.siliconflow.cn/v1
# LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
# LLM_API_KEY=...        # 由你本人填入，.env 已 gitignore，绝不提交
```

- `LLM_API_KEY` 为空时：真实 LLM 入口返回 409，前端显示"未配置"，演示 Agent 模式照常可用。
- **成本熔断**（默认保守，无需 key 也生效）：`LLM_KILL_SWITCH=1` 一键禁用真实 LLM 入口；
  `LLM_DAILY_MAX_CALLS=50` 限制每天真实 API 调用次数（本地 stub 不计费、不计入）；
  `LLM_MAX_STEPS=12` 限制单轮步数。额度在「实时运行」页的 LLM 状态行可见。
- 开发期**零真实外部调用**：Agent 循环用本地 stub（`scripts/stub_llm_server.py`）验证。
- 详见 [docs/LLM.md](docs/LLM.md)。建议在模型服务商侧设置消费限额/告警。

## MCP 接入

标准 MCP（SSE）：`http://127.0.0.1:8000/mcp/sse`，工具 `crm_read / crm_update / mail_send / crm_export_all / guard_check_status`。
示例客户端：`backend/venv/bin/python examples/mcp_client_demo.py --base http://127.0.0.1:8000`。
详见 [docs/MCP.md](docs/MCP.md)。

## 演示指南（评委 10 分钟走完）

详见 [docs/DEMO_V2.md](docs/DEMO_V2.md)。打开「实时运行」Tab（默认首页，SSE 实时推送）：

- **A 真实 LLM 自主执行**：新建任务 → 输入目标 →「真实 LLM 运行」→ 网关自动放行读操作 → 发邮件进入审批 → 在工具卡片上**内联批准** → 循环自动继续 → 发件箱落库 → 审计可查
- **B 越权与注入防护**：「演示攻击拦截」→ 客户 6 备注中的注入指令诱导 Agent 请求 `crm.export_all` → 网关 **deny** → 无执行 → 审计记录拒绝原因（展示 Agent 真实行为与网关真实判定）
- **C 人工急停**：批量任务运行中 → 顶栏「紧急停止」→ 未开始的动作全部 `blocked_by_stop` → 显式「恢复」后才能继续
- **D 外部 MCP 客户端**：运行示例客户端 → 工具发现 → `crm_read` 自动成功 → `mail_send` 在控制台审批 → `crm_export_all` 被拒绝 → 审计验证

## 测试

```bash
cd backend && venv/bin/python -m pytest tests/ -q   # V1 11 项 + V2 新增
python3 scripts/demo_e2e.py --base http://127.0.0.1:8000
cd frontend && npm run build
```

结果见 [docs/TEST_REPORT.md](docs/TEST_REPORT.md)。

## 项目结构

```
agent-guard/
  PLAN.md / PLAN_V2.md     实施计划与 API 契约
  README.md                本文件
  backend/app/
    gateway.py             单一网关：propose → adjudicate（Web/MCP/LLM 唯一入口）
    policy.py              外置策略引擎（纯函数）
    executor.py            受控执行器（执行前自查）
    audit.py               审计事件 + 哈希链
    mcp_server.py          MCP 服务器（官方 mcp SDK，/mcp/sse）
    llm_agent.py           真实 LLM Agent 循环（OpenAI-compatible）
    llm_routes.py          /api/llm/status, /api/tasks/{id}/run-llm
    demo_agent.py          确定性演示 Agent（与执行器/DB 写路径物理隔离）
  frontend/src/pages/Live.jsx   实时运行视图（SSE）
  scripts/stub_llm_server.py    本地 OpenAI-compatible 桩（开发测试用）
  examples/mcp_client_demo.py   MCP 示例客户端
  docs/  MCP.md  LLM.md  DEMO_V2.md  DEMO.md（V1 旧版，已被 DEMO_V2.md 取代） ARCHITECTURE_V2.md  TEST_REPORT.md  DEV_SUMMARY.md  PITCH_FRAMING.md  SUBMISSION_ROADMAP.md
```

## 已知限制

- 真实邮件发送：默认关闭（模拟写 outbox）。开启方式见 `.env.example` 的
  `REAL_MAIL_*` / `SMTP_*` 注释：`REAL_MAIL_ENABLED=1` + SMTP 配置 +
  `REAL_MAIL_ALLOWLIST` 白名单。启用后仅白名单地址可真实发出，其他一律拒绝
  并记 blocked 记录；真实发出后 outbox 标记 `real_sent=1`，审计记
  `mail.real_sent` 事件（to/subject，不记正文）。SMTP 密码只从 `.env` 读取，
  不进日志/审计/仓库。
- 开发期未使用真实 LLM key：真实模型端到端验证留待 Mac 验收（用户自行配置 key 后跑场景 A）。
- 管理/审批接口鉴权：默认无鉴权（本机演示，绑定 127.0.0.1）；如需暴露到局域网/公网，
  在 `.env` 设置 `GUARD_ADMIN_TOKEN`，管理与审批决议接口即要求 `X-Admin-Token` 请求头
  （前端顶栏"管理口令"输入框填入后自动携带）。
- Docker Compose 未在开发环境实测（环境无 Docker）；`start-mac.sh` 未在 macOS 实测。
- 前端未做真人点击联调（构建通过、接口契约检查通过）。
- 审计哈希链仅"可检测篡改"；单机演示，无多租户/复杂身份体系。
- 急停期间被阻止的动作为终态阻塞（`blocked_by_stop`），恢复后需新建任务重新规划。
