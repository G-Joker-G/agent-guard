# Agent Guard — 实施计划

> 黑客松 Demo：独立于 AI Agent 的执行控制层。任务书见 `../user/files/Agent_Guard_Muse.docx`。
> 用户确认：界面中文；本地开发于本云电脑 `~/workspace/agent-guard`；验收前**不推任何远程仓库**；
> 商业计划书 PDF 与 3 分钟旁白视频本次不做。

## 里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | PLAN.md + 脚手架 + API 契约 + git 初始化 | ✅ 2026-10-11 |
| M1 | 后端 P0 完成（FastAPI + SQLite + 策略引擎 + 审批 + 急停 + 审计） | ⬜ |
| M2 | 前端 P0 完成（React+Vite，中文 UI） | ⬜ |
| M3 | 后端自动化测试全绿 + E2E 演示脚本 | ⬜ |
| M4 | 打包：docker-compose / Dockerfile / start-mac.sh / .env.example / README | ⬜ |
| M5 | P1 完成（实时可视化、攻击模式、审计回放、一键重置） | ⬜ |
| M6 | 最终交付：测试报告、已知问题、截图、开发总结 | ⬜ |

取舍顺序（时间不足时）：P0 正确性 → 可重复演示 → Mac 一键运行 → P1 视觉效果。绝不为美观牺牲权限边界。

## 环境说明

- 云电脑：Python 3.12、Node 24、git 可用；**无 Docker**（`docker`/`docker compose` 均不存在）。
  → 本地验证改为直接运行进程（uvicorn + vite）；`docker-compose.yml` 照常提供给 Mac 端（Docker Desktop），
  并在 README 明确标注"compose 未在本环境实测"。

## 目录结构

```
agent-guard/
  PLAN.md  README.md  .env.example  docker-compose.yml
  backend/          # FastAPI + SQLite
    app/
      main.py        # 路由装配
      db.py          # SQLite 连接/建表/seed
      models.py      # 数据模型（SQLAlchemy）
      schemas.py     # Pydantic 请求/响应
      policy.py      # 外置权限策略引擎（纯函数，无副作用）
      demo_agent.py  # 确定性演示 Agent（只产出结构化请求；禁止 import executor/db 写路径）
      executor.py    # 受控执行器（执行前自查：急停/审批绑定/策略）
      audit.py       # 审计事件写入 + 哈希链
      seed.py        # 虚构客户数据
    tests/           # pytest
    requirements.txt
  frontend/         # React + Vite（中文 UI）
    src/  package.json  vite.config.js
  scripts/
    demo_e2e.py     # 三条演示路径的端到端脚本（直调后端 API）
    reset_demo.py   # 演示数据重置（调 POST /api/admin/reset）
  docs/
    DEMO.md         # 三条演示路径说明
    TEST_REPORT.md  # 测试命令与结果
  BLOCKERS.md       # 阻塞事项（如有）
```

## 安全架构（必须遵守）

```
用户任务 → demo_agent(只读提案) → 网关: policy.evaluate
   → allow → executor(复查急停+审批绑定) → 模拟工具 → 审计
   → needs_approval → 人工审批(绑定 request_hash+参数+有效期,一次一用) → executor → 审计
   → deny → 终止 + 审计
急停: system_state.emergency_stop=1 → 网关拒绝新动作；executor 执行前必查；仅显式 resume 恢复
```

- `demo_agent.py` 不得 import `executor` / `sqlite3` / 写库模块（测试会 grep 断言）。
- 所有受保护动作的放行判定只在服务端；前端状态仅做展示。
- 审批绑定：`scope_hash = sha256(tool + canonical_json(params))`；执行时校验审批存在、未使用、未过期、hash 一致，执行后标记已用。
- 审计哈希链：`hash = sha256(prev_hash|ts|event|detail)`，提供 `/api/audit/verify`；对外口径为"可检测篡改"，不宣称防篡改。

## API 契约（v1，前后端共同遵守）

Base URL: `http://localhost:8000`，所有业务路由前缀 `/api`。Content-Type: application/json。

### 基础
- `GET /api/health` → `{"ok": true, "simulation_mode": true, "version": "0.1.0"}`
- `GET /api/admin/status` → `{"emergency_stop": false}`

### 任务
- `POST /api/tasks` body `{"title": str, "scenario": "followup"|"export_attack"|"batch"}` → `{"id", "title", "scenario", "status": "created", ...}`
- `GET /api/tasks` → `[{id,title,scenario,status,created_at}]`
- `GET /api/tasks/{id}` → 任务详情 + `actions: [...]`
- `POST /api/tasks/{id}/plan` → 演示 Agent 生成结构化动作请求（status=proposed），返回 actions 列表
- `POST /api/tasks/{id}/advance` → 网关推进：对每个 proposed action 做策略评估；自动执行 allow 的；
  遇到 needs_approval 停下（task→pending_approval）；deny 则标记并继续；返回最新 task+actions。
  幂等：已终态 action 不重复处理。

### 动作
Action 对象：`{id, task_id, seq, tool, params, status, request_hash, decision, decision_reason, result, created_at}`
- tool 取值：`crm.read` / `crm.update` / `mail.send` / `crm.export_all`
- status 取值：`proposed|allowed|needs_approval|denied|approved|rejected|blocked_by_stop|executed|failed`
- `POST /api/actions/{action_id}/execute` → 网关执行单个动作（复查急停→复查策略/审批→executor→审计），返回 action。
  幂等：非可执行状态直接返回当前状态，不重复执行。

### 审批
Approval: `{id, action_id, scope_hash, status: pending|approved|rejected, approver, note, expires_at, used, decided_at}`
- `GET /api/approvals?status=pending` → 待审批列表（附带 action 的操作/目标/参数摘要/风险说明）
- `POST /api/approvals` body `{"action_id": int}` → 为 needs_approval 的 action 创建审批单（幂等：已有 pending 则返回现有）
- `POST /api/approvals/{id}/decide` body `{"decision": "approve"|"reject", "approver": "admin", "note": ""}` →
  approve 生成 scope 绑定（expires_at = now+30min）；reject 则 action→rejected。

### 急停（管理员）
- `POST /api/admin/stop` body `{"by": "admin"}` → emergency_stop=1；审计 `stop.engaged`；返回受影响的待执行动作数
- `POST /api/admin/resume` body `{"by": "admin"}` → 显式恢复为 0；审计 `stop.released`
- 急停期间：新 action 的 evaluate 直接 `blocked_by_stop`；execute 直接拒绝并审计 `action.blocked_stop`

### 审计
AuditEvent: `{id, ts, task_id, action_id, event, actor, detail, prev_hash, hash}`
- `GET /api/audit?task_id=&limit=200` → 按时间倒序
- `GET /api/audit/verify` → `{"ok": true, "checked": N}`（重算哈希链）

### 模拟数据
- `GET /api/customers` → 虚构客户列表（含 notes 字段；攻击模式客户的 notes 内嵌恶意指令）
- `GET /api/outbox` → 模拟发件箱（真实写入 DB 的发送记录）
- `POST /api/admin/reset` → 清空任务/动作/审批/审计/发件箱并重建种子客户数据，解除急停；审计 `data.reset`

### 策略规则（policy.py，至少这四类）
| # | 匹配 | 判定 | 风险说明 |
|---|---|---|---|
| 1 | tool=`crm.read` | allow | 只读客户信息，低风险 |
| 2 | tool=`crm.update` | needs_approval | 修改客户资料，需人工确认变更内容 |
| 3 | tool=`mail.send` | needs_approval（batch=true 时高风险标注） | 对外发送，内容需审核 |
| 4 | tool=`crm.export_all` | deny | 批量导出全部客户资料，禁止 |
| 5 | 其他未定义 tool | deny（默认拒绝） | 未知动作默认拒绝 |

### 演示 Agent（demo_agent.py，确定性）
- `followup`：`[crm.read(customer 1), mail.send(to=customer 1, subject/body 模板)]`
- `export_attack`：`[crm.read(customer X)]` → 规划器"读到" notes 中的注入指令（明确标注为模拟诱导）→ 追加 `crm.export_all` 请求
- `batch`：`[crm.read, mail.send×3(batch=true), crm.update]` 多步批量，用于急停演示
- 所有产出仅为结构化请求对象，不触碰执行器与数据库。

## 测试清单（pytest，backend/tests/）
1. 未定义 tool 默认拒绝；拒绝后 execute 不执行
2. `crm.update` 未审批时 execute 被拒绝（无审批=不执行）
3. 审批与请求绑定：篡改 params 后原审批失效（scope_hash 不匹配→拒绝执行）
4. 审批一次一用：重复 execute 不重复执行
5. 急停：stop 后新动作 blocked_by_stop；已 approved 未执行的 execute 被阻止
6. 恢复必须显式：无 auto-resume（stop 后 advance 不推进；只有 resume 接口能恢复）
7. 审计完整性：走完路径 A，关键事件（proposed/policy/approval/executed）全部存在且哈希链 verify 通过
8. 架构隔离：demo_agent.py 源码不含 `executor`/`sqlite3`/`import db`
9. E2E：`scripts/demo_e2e.py` 跑通 A/B/C 三条路径，断言 DB 真实变更（客户字段/outbox 记录）

## 打包
- `docker-compose.yml`：backend（uvicorn :8000）+ frontend（nginx :3000），`docker compose up` 一键启动
- `start-mac.sh`：检查 python3/node → 建 venv 装依赖 → 启动后端 → npm install/build → 静态服务前端 → 自动打开浏览器；附 `stop-mac.sh`
- `.env.example`：`BACKEND_PORT/FRONTEND_PORT` 等，无密钥
- README：架构图、安装、启动、演示步骤、三条路径说明、限制（Docker 未在本环境实测、Mac 未实测、模拟模式声明）

## 已知限制（先记下，README 同步）
- 云电脑无 Docker：compose 配置提供但未经本环境实测。
- 无法在用户 Mac 上实测：start-mac.sh 按脚本逻辑编写，标注"未在 macOS 实测"。
- 无真实 LLM：演示 Agent 为确定性模拟，UI 明确标注"模拟模式"。
