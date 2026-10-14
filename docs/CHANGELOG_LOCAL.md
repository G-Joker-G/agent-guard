# Agent Guard 本地更新日志（未推送远端）

本文档记录 2026-10-13 白天两轮本地审计与加固的全部改动。
远端 main 分支保持 2026-10-13 凌晨的验收基线（`db805d7`）不动；
以下改动只存在于本机 git，需用户验收确认后才推。

---

## 第一轮（commit `3ec6fe2`）：成本熔断 + 前端错误边界 + 前端/文档审计修复

### 新增：真实 LLM 成本熔断（`backend/app/llm_budget.py`）
- **依据**：用户明确说过"没设限额机制就不给真实 API Key"。此前代码与文档
  （`docs/LLM.md` 验收步骤 1）都只写"建议在服务商控制台设限额"，产品侧零防护。
- **内容**：三重保险，默认保守——
  1. `LLM_KILL_SWITCH=1`：一键禁用真实 LLM 入口（`/run-llm` 直接 409，不起线程）；
  2. `LLM_DAILY_MAX_CALLS=50`：每天**真实** API 调用上限，超限拒绝启动、循环中每步复查；
  3. `LLM_MAX_STEPS=12`：单轮最大步数（每步 = 1 次 API 调用）。
  "真实调用"定义为 base_url 非回环地址；本地 stub 不计费、不计入额度（但同样受
  max_steps 约束）。额度持久化在 SQLite `system_state`（`llm_calls_YYYY-MM-DD`），
  重启不丢失；`/api/admin/reset` 不清零额度（演示重置不能重置费用额度）。
  `/api/llm/status` 返回额度状态，前端实时页显示"今日调用 x/50"。
- **注意**：这是调用次数熔断，不是金额换算；金额级限额仍建议在服务商控制台设置。
- **测试**：新增 `backend/tests/test_v2_budget.py` 7 项（kill switch 路由/直接调用、
  额度用尽零网络拦截、stub 不计费、`LLM_MAX_STEPS` 生效、非法 env 回退默认值、
  status 接口含额度字段且不泄露 key）——全绿。

### 新增：前端 React Error Boundary（`frontend/src/ErrorBoundary.jsx`）
- **依据**：2026-10-13 凌晨 `Demo.jsx:196` 一个未定义变量导致整树黑屏。
  同类问题今后只崩当前 Tab，显示错误卡片（重试/刷新按钮），其他 Tab 不受影响。
- **内容**：`App.jsx` 每个 Tab 独立包裹（`key={tab}` 使切换 Tab 重置错误态），
  `main.jsx` 顶层再兜一层。
- **未验证**：错误卡片未做真人点击验证（构建通过）。

### 前端真实 bug 修复（审计逐项核实）
1. `Data.jsx`：发件箱"收件人"列误写 `m.to || m.recipient`，后端字段是 `to_email`——
   该列此前永远显示"—"。已改 `m.to_email`。
2. `labels.js`：`TASK_STATUS` 缺 `planned`/`in_progress`/`failed`（后端真实下发的状态），
   演示中途徽章显示英文原文。已补中文映射。
3. `Live.jsx`：SSE 重连全量重播污染时间线 + 每个重播事件触发 `loadTaskDetail` 造成
   API 请求风暴。已按事件 id 去重（切换任务时清空去重集合）。
4. `Demo.jsx`：`s.decision` 是自由文本（"演示成功"等），误用 `ActionBadge` 渲染出
   灰色"未知"徽章。改为语义正确的成功徽章；删死代码 `<ErrorBox error={''}/>` 与未用 import。
5. `Live.jsx`："继续推进"按钮 disabled 条件加 `running`，防止与运行中的 Agent 并发推进。
6. `Live.jsx`/`styles.css`：实时时间线 div 版补上竖线/圆点样式（与审计页一致）；
   表格 `td` 加 `word-break`（长参数摘要不撑开布局）。

### 文档修复（审计逐项核实）
- `DEMO_V2.md`：MCP 示例命令 `python../examples` 补空格（按文档逐字敲会失败）；
  场景 B 补上种子数据中的模拟注入指令原文（引号内原为空）。
- `MCP.md`：Web 控制台地址 `http://127.0.0.1:8000`（只有后端 API）→ 改为前端地址。
- `LLM.md`：验收步骤编号跳过 4 → 重编号；env 表格补三个熔断变量；验收步骤 1 说明熔断。
- `DEMO.md`：标注为 V1 旧版、已被 `DEMO_V2.md` 取代。
- `README.md`：项目结构补全 docs 列表；"已知限制"加成本熔断与鉴权口径说明。
- `TEST_REPORT.md`：接口契约"无遗漏"收紧为**路径级**口径，并如实记录本次发现的两例
  字段级不一致（已修复）。

### 测试证据（第一轮，云电脑亲自跑过）
- `pytest backend/tests/ -q` → 30 passed（原 23 + 新增 7）
- `cd frontend && npm run build` → 通过（37 modules）
- 后端 `:8123` + `python3 scripts/demo_e2e.py` → A/B/C 全绿

---

## 第二轮（commit `f4ad262`）：后端安全加固（审计 P1/P2）

审计结论：无阻断演示主路径的 P0；但 6 个 P1 中 2 个削弱核心安全承诺（一次一用、
审批 scope 绑定），1 个让审计链在并发下分叉。以下逐项修复。

### P1-1 审批"一次一用"并发竞态（`executor.py`）
- **问题**：`_find_valid_approval()` 查到 `used=0` → 执行 → 置 `used=1`，查与置分两步。
  两个并发 `/execute` 可同时通过检查，各执行一次（如连发两封邮件）。
- **修复**：`_claim_approval()` 原子认领——`UPDATE approvals SET used=1
  WHERE id=? AND used=0`，按 rowcount 决定是否执行；**认领在执行之前**
  （非法输入不能消耗一次性审批，见 P1-5）。
- **测试**：`test_concurrent_double_execute_single_execution`（两线程，结果为
  `[200,409]` 或 `[200,200]` 幂等，但发件箱恒为 1）+
  `test_claim_approval_is_atomic`（确定性单测）。

### P1-2 `decide_approval` 重算 scope_hash（`main.py`）
- **问题**：批准时用**当前** `action.params` 重算并覆盖创建时的 `scope_hash`——
  攻击者在"审批单创建后、批准前"篡改 params，批准动作会把篡改后的参数重新合法化，
  网关 scope 校验随即通过；创建时绑定的意义被架空。
- **修复**：批准时不再重算，沿用创建时的绑定；篡改过的 params 在执行器复查时以
  `approval_scope_mismatch` 拒绝。
- **测试**：`test_tampered_params_not_rebound_on_approve`（篡改→批准→执行 409，
  发件箱为 0）。

### P1-3 `decide_approval` 并发双批（`main.py`）
- **问题**：先查 `pending` 后置状态，两个并发批准请求可同时通过检查，
  last-write-wins 并产生两条 `approval.approved` 审计事件。
- **修复**：原子认领 `UPDATE ... WHERE status='pending'`，rowcount 为 0 则 409。
- **测试**：`test_concurrent_double_decide_single_winner`（`[200,409]`，
  审计里只有一条 `approval.approved`）。

### P1-4 审计哈希链并发分叉（`audit.py`、`models.py`、`db.py`）
- **问题**：`append_event` 先查"最后一条"取 `prev_hash` 再插入，非原子。
  LLM 循环线程（每步 `agent.step`）与人工批准并发时可读到同一 last，
  链分叉后 `verify()` 误报 `ok=False`。
- **修复**：`prev_hash` 唯一约束（`uq_audit_prev_hash`）+ 乐观并发——冲突时在
  savepoint 内回滚、重读 last 再试（最多 6 次，指数退避 + 抖动）。
  **刻意不用进程锁**：进程锁曾与 SQLite 写锁形成锁序死锁
  （execute 路径：DB 写→审计锁；append 路径：审计锁→DB 写），已实测复现。
  老库通过 `init_db` 轻量迁移补索引（`IF NOT EXISTS`，失败跳过不阻断启动）。
- **测试**：`test_concurrent_audit_writes_chain_intact`（8 线程 × 25 次，
  `verify()` ok 且 `checked>=200`）。

### P1-5 执行器非法输入校验（`executor.py`）
- **问题**：LLM 返回 `"updates": ["x"]` 等非 dict 输入时 `updates.items()` 抛
  `AttributeError`：REST 路径变 500 且无失败审计；MCP 路径异常直抛客户端。
  真实 LLM 验收时最可能踩到的坑。
- **修复**：`execute()` 入口校验——`params` 非 dict → `invalid_params`；
  `crm.update` 的 `updates` 非 dict → `invalid_updates`（校验在审批认领之前，
  非法输入不消耗一次性审批）。
- **测试**：`test_executor_rejects_non_dict_inputs`。

### P1-6 管理/审批接口鉴权开关（`main.py`、`api.js`、`App.jsx`）
- **问题**：`/api/admin/stop|resume|reset`、`/api/approvals/{id}/decide` 零鉴权。
- **修复**：可选开关 `GUARD_ADMIN_TOKEN`——**未设置时行为与之前完全一致**
  （本机演示零负担）；设置后上述接口要求 `X-Admin-Token` 请求头，否则 401。
  前端顶栏加"管理口令"小输入框（localStorage 持久化，自动随请求发送）。
- **测试**：`test_admin_token_gate`（无头/错头 401，对头 200）、
  `test_admin_token_unset_keeps_current_behavior`。
- **口径**：`README.md` 已知限制如实记录。

### P2-7 MCP 示例客户端（`examples/mcp_client_demo.py`）
- **问题**：`TERMINAL` 不含 `approved`——人工批准晚于网关 wait 超时（300s）时，
  动作停在 `approved` 无人执行，轮询空转 20 分钟后 `exit(1)`；
  另 `time.sleep(2)` 写在 async 函数里阻塞事件循环。
- **修复**：轮询到 `approved` 时补调一次 `POST /api/actions/{id}/execute`；
  `time.sleep` → `await asyncio.sleep`。

### P2-8 approved 分支带 approval_id（`gateway.py`）
- **问题**：wait-mode 批准后执行成功的结果里 `approval_id=None`，与
  rejected/stopped/timeout 分支不一致，调用方无法关联审批单。
- **修复**：approved 分支执行后 `res["approval_id"] = approval.id`。

### P2-9 MCP/LLM 任务状态（`gateway.py`）
- **问题**：`run_protected_tool` 建的任务状态永远 `created`，看板语义与 REST 不一致。
- **修复**：返回前按动作终态同步——`executed`→`completed`，其他终态→`failed`。

### P2-10 `run-llm` 的 goal 持久化（`llm_agent.py`）
- **问题**：goal 只进内存 messages，不写库不写审计，事后无法还原初始指令。
- **修复**：调用入口记一条 `agent.goal` 审计事件（含 goal 摘要 500 字）。
- **测试**：`test_agent_goal_audited`。

### P2-11 pending 审批单唯一（`models.py`、`gateway.py`、`db.py`）
- **问题**：`ensure_pending_approval` 先查后插，并发下可产生重复 pending 单（幽灵单据）。
- **修复**：部分唯一索引 `uq_approval_pending_per_action`（`action_id`
  `WHERE status='pending'`）+ 冲突时回滚本函数写入、重查返回已存在单；
  老库 `init_db` 轻量迁移补索引。

### P2-12 急停冻结任务状态（`main.py`）
- **问题**：全 `blocked_by_stop` 的 task 被 `_recompute_task_status` 算成 `completed`，
  看板误导。
- **修复**：含 `blocked_by_stop` 的终态任务显示 `stopped`（前端 `labels.js` 已有映射）。

### 附带：SQLite 并发写加固（`db.py`）
- **问题**：修 P1-1/P1-3 时实测发现——SQLite 的 SHARED→RESERVED **锁升级不吃
  busy 超时**（防死锁设计），先 SELECT 再 UPDATE 的并发写会立即报
  `database is locked`（500）而不是干净等待/409。
- **修复**：事务以 `BEGIN IMMEDIATE` 开始（SQLAlchemy 官方 pysqlite 配方：
  `connect` 事件置 `isolation_level=None` + `begin` 事件发 `BEGIN IMMEDIATE`），
  写锁在事务开始时一次拿到位；busy 超时 30s。
  附带修了一个自死锁：`init_db` 迁移里 `inspect(engine)` 在外层事务内拿第二个
  连接——改为 `inspect(conn)` 用同一连接。
- **测试**：上述并发测试本身即覆盖；独立复现脚本 10/10 干净（无 500）。

### 测试证据（第二轮，云电脑亲自跑过）
- `pytest backend/tests/ -q` → **44 passed**（原 30 + 新增 14），连续 3 轮全绿
- `cd frontend && npm run build` → 通过
- 后端 `:8124` + `python3 scripts/demo_e2e.py` → A/B/C 全绿

### 未验证 / 未做（诚实记录）
- 真实 key 的场景 A（等用户 Mac 验收时亲自配 key；熔断逻辑已用 stub + 单测覆盖）
- Docker Compose、`start-mac.sh` 的 macOS 实测（环境无 Docker/Mac）
- 前端真人点击（ErrorBoundary 错误卡片、管理口令输入框未做真人点击验证）
- `/api/events` SSE 长连接无自动化测试
- 同一 task 并发 `run-llm`（两个 Agent 循环交错）无测试、无互斥设计——已知限制
- P1-6 的 401 路径前端展示未做真人点击验证
