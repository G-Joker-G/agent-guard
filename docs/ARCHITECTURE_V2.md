# Agent Guard V2｜架构与开发总结

日期：2026-10-11　版本：0.2.0

## 一、V2 相对 V1 的变化

| 维度 | V1 | V2 |
|---|---|---|
| Agent | 确定性演示 Agent（唯一） | 演示 Agent + 真实 LLM Agent（OpenAI-compatible）+ 外部 MCP 客户端 |
| 网关 | 逻辑散在 main.py | `gateway.py` 单一入口：`propose → adjudicate`，Web/MCP/LLM 共用 |
| 审批等待 | 仅 Web 异步（advance 停下等人） | 新增阻塞等待模式（MCP/LLM 调用等待人工，可配超时） |
| 可视化 | 轮询式调试面板 | SSE 实时运行视图（事件源 = 审计表） |
| 接入 | 无 | 标准 MCP（SSE）服务器 |

## 二、核心架构决策

1. **单一网关**：`backend/app/gateway.py` 是所有受保护工具调用的唯一入口。
   `main.py` 的 `_advance_task` / `execute_action` 重构为委托调用，V1 的 11 个
   pytest 在重构后**零修改全绿**，证明语义守恒。
2. **三种裁决模式**：`adjudicate(mode=)` —— `advance`（Web 推进语义）、
   `execute`（单动作执行语义）、`wait`（MCP/LLM 阻塞等审批）。急停复查、
   策略重评、审批绑定复查在每种模式下都执行。
3. **审批等待不自动拒绝**：超时只返回 `approval_timeout` 错误，审批单保持
   pending（人工稍后仍可决策），客户端用 `guard_check_status` 续查。
   等待用全新 session 轮询，避免调用方 session 的 identity map 看到过期状态。
4. **事件源 = 审计表**：`/api/events`（SSE）直接增量推送审计事件；
   LLM 推理步骤记为 `agent.step` 审计事件一并推送。天然保证"所见即审计"，
   无需第二套事件总线。
5. **LLM 零执行权**：LLM 只产出 tool_calls；每个 call 经网关 propose +
   adjudicate；审批只能由控制台人工完成；系统提示词不含任何授权语义。
6. **MCP 2.x SDK**：`MCPServer("agent-guard")`，`sse_app()` 挂载到 FastAPI
   `/mcp`。工具处理器 `asyncio.to_thread` 调同步网关，不阻塞事件循环。

## 三、安全语义（继承 V1，测试锁定）

- 审批绑定 `scope_hash = sha256(tool + canonical_json(params))`，一次一用，30 分钟 TTL
- 急停：`blocked_by_stop` 终态；仅显式 resume 恢复；每次执行前复查
- 未定义动作默认拒绝；`crm.export_all` 永远 deny（纵深防御：策略层 + 执行器层双拒）
- 审计哈希链只宣称"可检测篡改"
- `demo_agent.py` 与执行器/DB 写路径物理隔离（grep 测试断言）

## 四、测试

`cd backend && venv/bin/python -m pytest tests/ -q` → **23 passed**

- V1 11 项：网关重构后零修改全绿
- V2-M1（MCP，8 项）：工具策略 enforcement（allow/approve/deny）、急停经 MCP 路径、
  审批等待超时、MCP 来源审计对应、`guard_check_status` 往返、工具名映射
- V2-M2（LLM，4 项）：无 key 时 status/409、stub 端到端 followup（含人工批准线程）、
  stub 注入攻击 deny

另有 live 验证（非 pytest，见 TEST_REPORT.md）：
- 示例 MCP 客户端真实连接 `/mcp/sse`：discover → `crm_read` 自动成功 →
  `mail_send` 经控制台审批后 executed → `crm_export_all` 被 deny → 审计链完整 →
  发件箱真实落库
- 前端 `npm run build` 通过

## 五、开发期问题与修复

1. **云电脑代理环境变量破坏 httpx2**：`HTTP_PROXY` 等变量导致 `httpx2.Client`
   构造时 URL 解析抛 `InvalidURL: Invalid port: ':1]'`。修复：本地回环地址
   （stub / 示例客户端）使用 `trust_env=False` 的客户端；真实远端域名保持默认。
   影响面：`llm_agent._make_client`、`examples/mcp_client_demo.py` 的
   `httpx_client_factory`。用户 Mac 上一般无此问题。
2. **子代理并发编辑冲突**：LLM 子代理修代理 bug 时误删了 `_utcnow` 定义，
   与我的集成修复撞车。教训：同一文件同一时间只允许一方编辑；已通过即时
   审查发现并让子代理恢复。

## 六、已知限制与后续扩展

已知限制（诚实记录）：
- 真实 LLM + 真实 key 的端到端验证留待 Mac 验收（用户自行填 key 后跑场景 A）
- Docker Compose 未在开发环境实测（环境无 Docker）；`start-mac.sh` 未在 macOS 实测
- 前端未做真人点击联调（构建 + 接口契约检查通过）
- 急停期间被阻止的动作为终态阻塞，恢复后需新建任务重新规划

后续扩展方向：
- 审批超时后的自动提醒（邮件/ webhook）与审批委托
- 基于角色的审批人（当前 approver 为自由文本）
- MCP 认证（当前无鉴权，演示用途）；streamable HTTP 传输
- 真实 CRM/邮件工具的受控适配器（保持网关不变，只换执行器后端）
- 多任务并发运行时，前端 live 视图的任务切换体验
- 为 LLM key 增加服务端侧的消费熔断（调用次数/金额上限）
