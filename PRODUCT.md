# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- 主要用户（演示场景）：黑客松评委与演示观众——在 3 分钟演示中需要一眼看懂"外置网关如何管住 Agent"。[推断]
- 真实使用场景的用户：开发/运营 AI Agent 的平台工程师与安全管理员——配置策略、审批敏感动作、必要时人工急停、事后审计追溯。[推断]

## Product Purpose

Agent Guard 是独立于 AI Agent 的执行控制层：所有工具调用必经服务端网关做权限裁决，敏感动作需人工审批，管理员可随时紧急停止，受控执行器只执行已授权动作，审计日志以哈希链保证不可篡改。

成功意味着：演示者能流畅展示"真实 LLM 自主执行 → 敏感步骤等待人工批准 → 越权/注入被网关拦截 → 人工急停"四条路径；工程师能把它作为 MCP/LLM Agent 的前置安全网关接入。[部分推断]

## Positioning

权限判定与执行控制完全在模型之外——模型只提议，网关才裁决。这是与"在 prompt 里加约束"或"靠模型自觉"方案的本质区别。审计即事件源：实时事件流直接来自审计表。

## Operating Context

- 演示工作流：场景 A 真实 LLM 自主执行并在敏感步骤等待人工批准；场景 B 越权与 prompt injection 被外置网关真实阻止；场景 C 执行期间人工急停；场景 D 外部 MCP 客户端接入。
- 首个演示场景是虚构 CRM 客户跟进与模拟邮件发送；CRM 数据与邮件发送为模拟，网关/审批/急停/审计/MCP/LLM 编排逻辑真实。
- 界面语言为中文；控制台通过 SSE 订阅实时事件流。

## Capabilities and Constraints

- 功能：外置策略引擎、审批范围绑定、一次一用审批、管理员急停与显式恢复、受控 CRM/模拟发件箱、审计哈希链、攻击模式、审计回放、演示数据重置、标准 MCP 接入（/mcp/sse）、OpenAI-compatible 真实 LLM Agent 循环、LLM 成本熔断（每日调用上限/单轮步数上限/一键停用）。
- 约束（硬）：只改前端展示与交互层；不得改变安全逻辑、权限判断、审批机制、审计机制、API 契约；不得为视觉伪造执行状态或安全数据——所有展示数据必须来自真实 API/SSE；零真实外部 LLM 调用。
- 技术约束：React + Vite + JSX 前端；Tailwind CSS v4 已装；shadcn/ui 组件（JSX 版）可用；深色模式（用户已拍板）。
- 未决：真实 LLM 验收需用户在 Mac 自行填 .env 的 key；Docker Compose 未实测。

## Brand Commitments

- 名称：Agent Guard，中文界面。
- 设计定位（用户拍板）：Developer Tools / AI Infrastructure / Security Dashboard / Professional SaaS Console；专业、简洁、现代；支持深色模式；避免廉价 AI 模板风。
- 工具链（用户拍板）：优先使用 Impeccable skill（项目内 `.impeccable/`，不全局安装），结合 shadcn/ui 构建组件体系。
- 语气：中文，技术文档式直接表达，无营销腔。

## Evidence on Hand

- 代码库 `~/workspace/agent-guard`：后端 FastAPI + SQLite（pytest 44/44），前端 React + Vite（`npm run build` 通过），E2E 演示脚本 A/B/C 全绿。
- 真实可演示数据：种子 CRM 客户数据、演示 Agent 三场景、MCP 示例客户端、本地 OpenAI-compatible stub。
- 设计输入：`docs/PITCH_FRAMING.md`（Nadella 七原则 → 功能映射）、`docs/DEMO_V2.md`。

## Product Principles

1. 诚实优先：展示的每个数字和状态都来自真实后端，绝不为演示效果编造。
2. 安全操作永远可达且位置固定：急停、审批决策按钮在任何界面一眼能找到。
3. 信息层级服务于"先看到风险，再看到细节"：待审批、被拒绝、急停状态优先于常规数据。
4. 控制台是工作台不是展台：密度合理、可扫读、键盘可达。

## Accessibility & Inclusion

[推断] 键盘可操作（审批/急停等关键操作应可键盘触发）；状态不只依赖颜色（配文字/图标）；中文排版避免截断。
