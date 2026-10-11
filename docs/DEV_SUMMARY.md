# 开发总结（2026-10-11）

## 做什么
为 MINMAX 黑客松构建 Agent Guard Demo：独立于 AI Agent 的执行控制层。
主张：Agent 只提方案，动手前过三道服务端门——外部策略（默认拒绝）→ 人工审批（绑定请求+参数+有效期，一次一用）→ 急停开关（每次执行前复查）。

## 怎么做的
- M0：PLAN.md（实施计划 + API 契约 v1 + 安全架构 + 测试清单），git 初始化。
- M1：后端（FastAPI + SQLite）：策略引擎 `policy.py`（纯函数）、确定性演示 Agent（与执行器/DB 写路径物理隔离，测试断言）、受控执行器（执行前自查急停/策略/审批绑定）、审计哈希链、7 个虚构中文客户（含 1 个注入载荷）。
- M2：前端（React 18 + Vite 6，中文深色 UI）：任务中心/审批中心/审计日志/客户数据/发件箱/演示六 Tab；常驻"模拟模式"横幅；全局急停按钮（恢复二次确认）；演示 Tab 一键跑 A/B/C 并展示每步后端调用。
- M3：pytest 11/11；`scripts/demo_e2e.py` 三条路径端到端全绿（断言 DB 真实变更/无副作用/审计完整）。
- M4：docker-compose.yml、Dockerfile×2、nginx.conf、start-mac.sh/stop-mac.sh、.env.example、README、docs/DEMO.md、docs/TEST_REPORT.md。
- M5：P1 收尾——攻击载荷可视化（演示 B 展示注入原文）、审计回放（按任务筛选时间线）、一键重置；修复 Demo.jsx 两个流程 bug（缺 ErrorBox 导入致页面崩溃；批准后误用 advance 而非 execute）。

## 关键设计决策
- 审批绑定用 `scope_hash=sha256(tool+canonical_json(params))`，执行器每次重算比对——改参数即失效，防"一次批准多次用/挪用"。
- 急停期间已批准动作的 execute 返回 409 但保留 approved 状态（恢复后可继续），blocked_by_stop 为终态——"恢复后才能开启新的执行"。
- 审计哈希链只宣称"可检测篡改"，不宣称防篡改。

## 遗留与风险
- Docker Compose、start-mac.sh 均未在目标环境实测（云电脑无 Docker；无 Mac）。
- 前端未做真人点击联调（构建通过 + 接口契约交叉检查通过）。
- 历史提交 M1/M2 曾误含 venv/node_modules（已从跟踪中清除，当前树干净；旧提交树仍含 junk，不影响使用）。
