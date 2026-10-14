# 测试报告

测试环境：云电脑 Ubuntu，Python 3.12.3，Node 24.20.0。测试日期 2026-10-11（V1）/ V2 同日。

## 2026-10-13 本地加固（未推送远端）

详见 [CHANGELOG_LOCAL.md](CHANGELOG_LOCAL.md)。本轮新增 21 项测试，全部零真实外部调用。

### 0. 全量回归

命令：`cd backend && venv/bin/python -m pytest tests/ -q`

结果：**44 passed**（V1 11 + V2 12 + 成本熔断 7 + 安全加固 14），连续 3 轮全绿。

新增测试文件：
- `tests/test_v2_budget.py`（7 项）：kill switch（路由/直接调用）、额度用尽零网络拦截、
  stub 不计费、`LLM_MAX_STEPS` 生效、非法 env 回退、`status` 含额度且不泄 key。
- `tests/test_v2_hardening.py`（14 项）：并发双执行单次生效、并发双批单胜者、
  篡改 params 批准后执行被拒、8 线程审计写链完整、非法输入类型、admin token 开关、
  审批过期、wait 中途急停、急停任务 stopped、agent.goal 审计、max_steps 耗尽、
  run_llm_task 无 key 直接调用、原子认领单测。

### 1. 并发专项（本轮实测发现并修复的真问题）

- 修 P1-1/P1-3 时发现：SQLite 的 SHARED→RESERVED **锁升级不吃 busy 超时**，
  先 SELECT 再 UPDATE 的并发写会立即报 `database is locked`（500）。
  已改事务 `BEGIN IMMEDIATE`（写锁在事务开始时一次拿到）；独立复现脚本 10/10 干净。
- 修 P1-4 时发现：进程锁 + SQLite 写锁会形成**锁序死锁**（execute 路径 DB 写→审计锁；
  append 路径审计锁→DB 写），已实测复现；改用 `prev_hash` 唯一约束 + savepoint 重试
  （乐观并发，不引入新锁）。
- `init_db` 迁移曾因 `inspect(engine)` 在外层事务内拿第二个连接而单线程自死锁，
  已改为 `inspect(conn)`。

### 2. 未验证项（诚实记录，2026-10-13）

- **真实 LLM + 真实 key 的端到端**：留待 Mac 验收（用户自行在 `.env` 填 key 后跑场景 A）；
  熔断逻辑已用 stub + 单测覆盖。
- **Docker Compose 未实测**：开发环境无 Docker。
- **start-mac.sh 未在 macOS 实测**。
- **前端未做真人点击联调**：ErrorBoundary 错误卡片、管理口令输入框未做真人点击验证；
  构建通过。
- **`/api/events` SSE 长连接**：无自动化测试（冒烟验证通过）。
- **同一 task 并发 `run-llm`**：无测试、无互斥设计——已知限制。
- **P1-6 的 401 路径前端展示**：未做真人点击验证。

## V2 新增（2026-10-11）

### 0. 全量回归

命令：`cd backend && venv/bin/python -m pytest tests/ -q`

结果：**23 passed**（V1 11 项零修改全绿 + V2 12 项）

### 1. V2-M1 MCP 测试（tests/test_v2_mcp.py，8 项）

| 用例 | 覆盖点 |
|---|---|
| test_1_allow_path_mcp | `crm_read` 经网关 allow，真实执行返回客户数据 |
| test_2_approval_path_mcp | `mail_send` 建审批单→批准→执行→outbox 落库 |
| test_3_deny_path_mcp | `crm_export_all` 被拒且无副作用 |
| test_4_stop_blocks_mcp_call | 急停后 MCP 调用 → blocked_by_stop，无执行 |
| test_5_approval_wait_timeout | `GUARD_APPROVAL_TIMEOUT=2` → approval_timeout 错误；审批单仍 pending |
| test_6_audit_chain_for_mcp_origin | origin=mcp 的动作有完整审计事件链 |
| test_7_guard_check_status_roundtrip | 状态查询往返 |
| test_8_tool_name_mapping | MCP 工具名→网关工具名映射 |

### 2. V2-M2 LLM 测试（tests/test_v2_llm.py，4 项）

全部只打本地 stub（`scripts/stub_llm_server.py`，127.0.0.1），**零真实外部 LLM 调用**。

| 用例 | 覆盖点 |
|---|---|
| test_llm_status_unconfigured | 无 key 时 status.configured=false，且不泄露 key |
| test_run_llm_without_key_returns_409 | 无 key 时 run-llm 返回 409 llm_not_configured |
| test_followup_loop_end_to_end | stub 驱动完整循环：read 放行执行 → mail 人工批准后执行 → outbox 落库；审计含 agent.step |
| test_export_attack_denied | stub 在读到注入后诱导出 crm.export_all → 网关 deny，无副作用 |

### 3. Live 验证（非 pytest，真实进程）

- **场景 D（MCP 真实联调）**：后端 live 启动后，
  `backend/venv/bin/python examples/mcp_client_demo.py --base http://127.0.0.1:18002`
  全绿：工具发现 → `crm_read` 自动成功 → `mail_send` 经 REST 审批后 executed →
  `crm_export_all` 被 deny → 审计链（proposed→policy→approval.created→approved→executed）完整 →
  发件箱真实写入 1 封。证明外部 Agent 的每次调用都经过网关裁决。
- **前端构建**：`cd frontend && npm run build` 通过（含新增 Live.jsx）。
- **SSE 事件流**：`/api/events?since=0` 真实推送审计事件（冒烟验证）。

### 4. 未验证项（诚实记录，V2）

- **真实 LLM + 真实 key 的端到端**：留待 Mac 验收（用户自行在 `.env` 填 key 后跑场景 A）。
- **Docker Compose 未实测**：开发环境无 Docker。
- **start-mac.sh 未在 macOS 实测**：仅 `bash -n` 语法检查；V2 增加了 `.env` 加载与 LLM key 提示。
- **前端未做真人点击联调**：构建通过、接口契约交叉检查通过；Live 视图的 SSE 实时性留待验收点击验证。
- **云电脑代理环境变量坑**：`HTTP_PROXY` 等会导致 httpx2 构造失败（`InvalidURL: Invalid port`）；
  已在 `llm_agent._make_client` 与示例客户端中对本地回环地址使用 `trust_env=False` 规避；
  用户 Mac 上一般无此问题。

---

## V1（2026-10-11）

## 1. 后端自动化测试（pytest）

命令：`cd backend && venv/bin/python -m pytest tests/ -q`

结果：**11 passed**（0 失败）

| 用例 | 覆盖点 |
|---|---|
| test_1_undefined_tool_denied_and_not_executed | 未定义 tool 默认拒绝；拒绝后 execute 不执行 |
| test_2_update_without_approval_rejected | `crm.update` 未审批时 execute 被拒绝 |
| test_3_tampered_params_invalidate_approval | 篡改 params 后原审批失效（scope_hash 不匹配） |
| test_4_approval_single_use | 审批一次一用；重复 execute 无副作用 |
| test_5_emergency_stop | 急停后新动作 blocked_by_stop；已批准未执行的 execute 被阻止 |
| test_6_no_auto_resume | 无自动恢复；只有显式 resume 能解除 |
| test_7_audit_integrity_path_a | 路径 A 关键审计事件齐全；哈希链 verify 通过 |
| test_8_demo_agent_isolation | demo_agent.py 源码不含 executor/sqlite3/import db |
| test_9_e2e_path_a_followup | 路径 A（含 DB 真实变更断言） |
| test_9_e2e_path_b_export_attack | 路径 B（含无副作用断言） |
| test_9_e2e_path_c_batch_with_stop | 路径 C（含急停/恢复断言） |

唯一 warning：starlette TestClient 关于 httpx 的 deprecation 提示，不影响功能。

## 2. 端到端演示脚本（直调 live 后端 HTTP API）

命令：`python3 scripts/demo_e2e.py --base http://127.0.0.1:8000`（需先启动后端）

结果：**路径 A / B / C 全部通过**，每一步均为真实 HTTP 调用并断言后端状态：
- A：读放行执行、邮件走审批、批准后执行、发件箱真实写入、重复执行无副作用、审计事件齐全、哈希链校验通过
- B：注入诱导出 export 请求、策略拒绝、强行执行无效、无副作用、审计记录拒绝原因
- C：急停后全部动作 blocked_by_stop、已批准动作执行前被拦截、显式恢复后可执行、审计含 stop.engaged/released

## 3. 前端构建

命令：`cd frontend && npm run build` → 通过（vite v6.4.4，35 modules）。

前后端接口契约交叉检查（路径级）：前端调用的全部 `/api/*` 路径均对应后端已实现的路由（脚本比对，无遗漏）。
> 口径说明：以上仅为路径级比对，未覆盖字段级契约。2026-10-13 前端审计发现两例字段级不一致（发件箱 `to_email` 误写 `to`；任务状态枚举缺 `planned/in_progress/failed`），已修复。

## 4. 未验证项（诚实记录）

- **Docker Compose 未实测**：开发环境无 Docker，`docker-compose.yml` + Dockerfiles 按标准写法提供，未经构建/启动验证。
- **Mac 未实测**：`start-mac.sh` 按脚本逻辑编写并通过 `bash -n` 语法检查，未在 macOS 上真实运行。
- **前端未做真人点击联调**：构建通过、接口契约交叉检查通过；完整点击流验证留待用户 Mac 验收。
- 无真实 LLM / 真实邮件 / 真实 CRM（设计如此，界面已声明模拟模式）。
