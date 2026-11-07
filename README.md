# Agent Guard V2 ｜ 企业级 AI Agent 可信执行与安全控制平台

> **🏆 MINMAX 粤港澳大湾区创客 AI Agent 黑客松挑战赛参赛作品**  
> **创作者 / 团队**：[易星衍 / YIXINGYAN — AI Native Builder](https://yixingyan.com/) ｜ 博客：[https://blog.yixingyan.com/](https://blog.yixingyan.com/)  
> **核心哲学**：*“We need to separate the supply of intelligence from the authority over it.”* —— Satya Nadella, 2026

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](backend/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](backend/)
[![React 18](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB.svg)](frontend/)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-Anthropic%20MCP-8A2BE2.svg)](docs/MCP.md)
[![Tests Passing](https://img.shields.io/badge/Pytest-50%2F50%20Passing-success.svg)](backend/tests/)
[![License MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 快速通道：参赛交付材料直达

- 📄 **商业计划书 (Business Plan)**：[Agent_Guard_商业计划书.pdf](docs/Agent_Guard_商业计划书.pdf) ｜ [Markdown 完整版](docs/BUSINESS_PLAN.md)
- 🚀 **评委 3 分钟免 Key 极速评测指南**：[docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) *(无需申请外部 API Key，开箱即测)*
- 🎬 **演示视频 (1080P MP4 交付件)**：[docs/Agent_Guard_Demo_1080p.mp4](docs/Agent_Guard_Demo_1080p.mp4) ｜ [分镜与解说词脚本](docs/VIDEO_SCRIPT.md)
- 📐 **系统架构与技术白皮书**：[docs/ARCHITECTURE_V2.md](docs/ARCHITECTURE_V2.md) ｜ [测试报告 (50/50)](docs/TEST_REPORT.md)

---

## 项目定位：解决企业不敢放权的核心死穴

大模型正在从“对话助手”演进为具备工具调用能力的“自主智能体（Autonomous Agents）”。然而在企业真实业务场景中，**间接提示词注入（Prompt Injection）、越权操作与概率性幻觉**让企业面临巨大合规与资产外泄风险，导致“技术可行但业务不敢上线”。

**Agent Guard 是独立于 AI Agent 的执行控制层**：
- **模型只管思考与规划（Supply of Intelligence）**；
- **能否调用、何时执行、改动什么，由模型之外的单一网关裁决（Authority Over It）**；
- 继承 1970 年代经典安全体系 **Reference Monitor（引用监视器）** 理论，实现大模型智能与业务执行权力的物理解耦。

```
                    ┌─ Web 控制台（实时运行视图，SSE 事件流） ─┐
                    │  工具请求卡片 → 策略判定 → 内联审批/拒绝  │
                    │  全局急停按钮 · 实时审计时间线            │
                    └──────────────────┬──────────────────────┘
                                       │ 人工决策 / 急停
用户任务 ── Agent ──→  单一网关 gateway.py  ←── 外部 MCP 客户端（/mcp/sse 标准协议）
（演示/LLM/        propose → policy.evaluate → allow 直接执行
  MCP）            → needs_approval → 审批单 → 阻塞等待人工（可配置超时）
                   → deny → 拒绝 + 审计
                          ↓
                    受控执行器（执行前复查：急停→策略→审批绑定）
                          ↓
                    真实/模拟业务系统 → 审计日志（哈希链，可检测篡改）
                          ↓
                    /api/events（SSE，事件源 = 审计表）
```

---

## 核心安全语义与壁垒

1. **单一入口强隔离**：所有工具调用必经 `gateway.adjudicate()`，前端状态不是安全边界，Agent 绝无直通底层执行器的路径。
2. **三态自适应策略**：
   - `allow`：只读安全操作毫秒级放行（如 `crm_read`）；
   - `needs_approval`：高危写操作强制挂起（如发邮件、改客资、调资金），等待人工审核；
   - `deny`：越权与敏感数据全量导出硬阻断（如 Prompt Injection 诱导调用的 `crm_export_all`）。
3. **密码学审批绑定**：审批单严格绑定 `scope_hash = sha256(tool + canonical_json(params))`，一次一用，30 分钟失效，改参数即失效。
4. **一键全局人工急停（Kill Switch）**：顶栏常驻急停按钮，瞬间封锁网关，未开始动作全部转为终态 `blocked_by_stop`，需管理员显式二次确认恢复。
5. **防篡改审计哈希链**：基于 SHA-256 构建的轻量级审计哈希链，每一笔决策真实落盘、环环相扣，提供司法级不可篡改证据链。
6. **Anthropic 标准 MCP 原生接入**：提供 `/mcp/sse` 标准端点，外部任意 Agent（Claude Desktop、Cursor 等）接入同样受网关约束。

---

## 10 秒快速启动

### 方式一：Windows 本地一键启动（推荐）
直接双击运行根目录下的 **`start-windows.bat`**  
*(或在 PowerShell 执行 `.\start-windows.ps1`)*，自动检查环境、安装依赖、启动服务并弹出浏览器。  
停止服务请双击运行 **`stop-windows.bat`**。

### 方式二：Mac / Linux 本地脚本
```bash
chmod +x ./start-mac.sh ./stop-mac.sh
./start-mac.sh
# 停止运行：./stop-mac.sh
```

### 方式三：Docker Compose 一键启动
```bash
docker compose up --build
# 前端：http://localhost:3000（或 :5173）  后端：http://localhost:8000
```

---

## 评委 3 分钟极速评测路径 (无需任何 API Key)

打开控制台默认进入「实时运行」页，系统内置确定性演示 Agent，零外部模型调用成本：

- **场景 1（5秒看懂核心价值）：Prompt Injection 注入攻击拦截**  
  点击左上方「演示攻击拦截」→ Agent 读取客户 6 备注中的恶意注入指令被诱导请求导出全部客资 → 网关瞬间判定 **`deny` 拒绝** → 审计实时记录，数据零外泄！
- **场景 2（1分钟体验人机协同）：高危操作审批与 scope 绑定**  
  点击「演示 Agent 运行」→ 读操作自动放行，外发邮件被挂起为 **`needs_approval`** → 在卡片上点击「批准执行」→ 邮件落入发件箱，审计链完整闭环。
- **场景 3（30秒体验紧急制动）：全局人工急停**  
  批量任务运行中点击顶栏红色「紧急停止」→ 未开始动作瞬间转为 **`blocked_by_stop`** 终态被丢弃。
- **场景 4（生态扩展）：外部 MCP 客户端调用**  
  终端运行 `python examples/mcp_client_demo.py --base http://127.0.0.1:8000`，体验外部 Agent 同样受到安全网关严格约束。

> 若评委希望接入真实大模型进行自由测试，可在根目录复制 `.env.example` 为 `.env` 并填入 `LLM_API_KEY`（如 DeepSeek-V4），重启后点击「真实 LLM 运行」即可。

---

## 自动化测试验证

全量 50 项单元与集成测试均锁定通过：
```bash
# 1. 后端 50 项安全用例全量测试
cd backend && venv/bin/pytest tests/ -q

# 2. 端到端 A/B/C 场景全链路 HTTP 测试
python scripts/demo_e2e.py --base http://127.0.0.1:8000

# 3. 前端生产打包构建验证
cd frontend && npm run build
```

---

## 团队与创作者

- **主创**：[易星衍 / YIXINGYAN — AI Native Builder](https://yixingyan.com/)
- **专业领域**：企业 AI 落地 · AI 原生构建 · 出海数字基础设施 · 计算机可信执行工程
- **联系与探讨**：[seniol9368187@gmail.com](mailto:seniol9368187@gmail.com) ｜ 个人主页：[https://yixingyan.com/](https://yixingyan.com/)
