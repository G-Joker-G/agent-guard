# Agent Guard 控制台设计规范（DESIGN_SPEC）

> 工具：Impeccable skill（项目内 `.impeccable/`）+ shadcn/ui（JSX）+ Tailwind CSS v4
> 模式：Operate（工作台）· 构建路径：code-led（Impeccable 规则：Operate  surface 一律 code-led）
> 方向已由用户拍板：shadcn/ui、现代视觉；定位 Developer Tools / AI Infrastructure / Security Dashboard / Professional SaaS Console
>
> **2026-10-14 视觉转向（用户反馈"太沉闷极客，要清爽"）**：默认浅色清爽主题（参考 Linear / Vercel / Stripe Dashboard 的现代 SaaS 气质），深色模式保留切换入口。信息架构（分组导航、按钮收敛、总览 Dashboard、Cmd+K、审计时间线、急停固定位置）保持不变，只重做视觉层。

## 一、现状设计审计（2026-10-14，headless Chromium 逐页截屏）

1. **窄栏居中**：所有页面挤在 ~1100px 居中列，两侧大片黑空地——控制台应是全宽工作台。
2. **顶部噪音**：蓝色小字横幅（sim-banner）占一整行；header 里品牌 + 7 个平铺导航按钮 + 状态文字 + 口令输入框 + 紧急停止全部挤在一行，层级混乱。
3. **导航无分组**：7 个 Tab 平铺，"找按钮难"的根源；审批计数藏在按钮文字"审批中心（1）"里。
4. **说明书式文案**：实时运行页有一大段使用说明，像手册不像控制台。
5. **按钮散落三处**：新建场景×3 / 演示运行×2＋继续推进 / 目标输入＋真实 LLM 运行——样式不统一、位置分散。
6. **信息冗余**：工具卡片"网关判定：放行 只读客户信息，低风险 风险：low"——判定与风险重复出现。
7. **审计日志 = JSON 直 dump**：时间线直接打印原始 JSON，可读性差。
8. **空态占半屏**：实时时间线"等待事件…"占去右侧一半。
9. **无总览 Dashboard**：任务书要求的"Dashboard 总览"不存在。
10. **无设计语言**：黑底＋默认蓝按钮，无统一 token；表格/徽章样式简陋。

## 二、方向契约（Direction Contract）

- **THESIS**：这是一个清爽的现代 SaaS 安全工作台——安静、精确、大量留白；拒绝霓虹赛博朋克、深夜极客风与廉价 AI 模板风（渐变字、玻璃拟态、装饰性网格一律不用）。
- **OWN-WORLD**：白 / 极浅灰底色 + 一支克制的主蓝（#2563eb）；细边框代替厚重卡片，轻阴影（shadow-sm）；语义色只做"状态的信使"，浅色下用 600 系降低饱和度但保证对比度（红=危险/拒绝，琥珀=待审批/警告，绿=通过/成功，天蓝=信息）；中文系统字体栈，数字用 tabular-nums，mono 只给哈希/ID/工具名；圆角 10px 卡片 / 8px 控件。
- **STORY**：进来先看到"系统是否安全、有什么等我处理"（总览）→ 深入实时运行看 Agent 在做什么 → 审批/急停永远一键可达。
- **FIRST VIEWPORT**：左侧白色侧边栏（分组导航），顶部栏左为搜索触发器（⌘K）、右为主题切换 / 连接状态 / 管理口令 / 固定红色的紧急停止；内容区全宽浅灰底，白色卡片承载内容。
- **SIGNATURE MOVE（Operate 允许的一个标志性手法）**：**网关裁决流水线**——"提议 → 网关裁决 → 审批 → 执行"四段式状态条，颜色即状态，用在工具请求卡片与任务详情。这是产品机制（模型只提议、网关才裁决）的可视化，不是装饰。浅色下用淡色底 + 600 系文字。
- **FINISH**：unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## 三、信息架构（新 → 旧对照）

| 新导航（侧边栏分组） | 旧 Tab | 说明 |
|---|---|---|
| 监控：总览 Dashboard（新增） | — | 网关状态/待审批/任务/今日 LLM 调用＋最近事件，全部来自真实 API |
| 监控：实时运行 | 实时运行 | 场景启动器收拢为一张卡片；工具卡片改用裁决流水线 |
| 管控：任务中心 | 任务中心 | 表格 shadcn 化 |
| 管控：审批中心 | 审批中心 | 批准/拒绝固定右列；badge 计数移到导航 |
| 管控：审计日志 | 审计日志 | 时间线重做：中文事件标签＋关键字段摘要，JSON 折叠 |
| 数据：客户数据 / 发件箱 | 客户数据 / 发件箱 | 二级 Tabs 合并为"数据"一组 |
| 系统：演示 | 演示 | 演示路径卡片化 |

顶栏（固定）：页面标题 ｜ 搜索（⌘K）｜ 事件流连接状态 ｜ 管理口令（锁图标 popover，原 header 输入框移入）｜ **紧急停止**（永远右端、永远红色）。

## 四、设计 Tokens（Tailwind v4 `@theme inline` + `:root` / `.dark`，见 `frontend/src/index.css`）

主题实现：`@theme inline` 把 `--color-*` 映射到 `--background` 等运行时变量；`:root` 放浅色值（默认），`.dark` 类覆盖深色值。顶栏有浅/深色切换按钮（默认浅色，localStorage `guard_theme` 持久化）。

**浅色（默认）**：
- `--background: #f7f8fa`（极浅灰画布） `--card: #ffffff` `--border: #e7e9ed` `--input: #dcdfe4`
- `--foreground: #1b1e23` `--muted-foreground: #6b7280`
- `--primary: #2563eb`（克制主蓝） `--accent: #e8eefc` / `--accent-foreground: #1d4ed8`（导航 hover 淡蓝底）
- `--destructive: #dc2626`（急停/拒绝，永远红色）
- 语义：`--success #16a34a` / `--warning #d97706` / `--info #0284c7`（600 系，徽章为 15% 淡底 + 600 系文字，对比度 ≥ 4.5:1）
- 卡片：白底 + 1px `#e7e9ed` 边框 + `shadow-sm`；滚动条拇指 `#cdd2d9`；代码块（审计详情）浅灰底 `#f1f3f5`

**深色（保留切换入口）**：沿用上一版 token（`--background #0b0e14`、`--primary #4c8dff` 等），与浅色各自独立成稿、非机械反转。

- 前景/次级文字对比度 ≥ 4.5:1；`--font-sans` 中文系统栈；`--font-mono` 等宽（哈希/ID/工具名）
- 间距：页面 `p-6 lg:p-8`；卡片 `rounded-[10px] border bg-card`；标题字号阶梯 20/16/14；行高 1.65

## 五、组件体系（`frontend/src/components/`）

沿用 shadcn/ui（JSX 化）：button（含 success/warning 语义变体）、badge（含 success/warning/info/muted/destructive）、card、table、input、dialog、command（⌘K）、tooltip、separator、skeleton、alert。
新增：`status.jsx`（TaskBadge/ActionBadge/DecisionBadge/RiskBadge/EventBadge/OriginBadge，状态→语义色的唯一映射）、`layout.jsx`（AppShell 侧边栏＋顶栏、PageHeader、Stat、EmptyState）、`palette.jsx`（全局命令面板）、`pipeline.jsx`（网关裁决流水线）。

## 六、页面要点

1. **总览**：4 张 Stat（网关状态/待审批/任务总数/今日 LLM 调用 x/50）＋ 待审批快捷表 ＋ 最近审计事件；空态给引导。
2. **实时运行**：顶部"场景启动器"卡片（新建场景＋演示运行＋真实 LLM 收拢，按钮按主/次/危险分级）；下方左右分栏：工具请求卡片（裁决流水线＋内联审批）｜ 实时审计时间线。
3. **任务中心/审批中心/数据/演示**：保留全部数据逻辑与 API 调用，只换皮肤与布局；审批备注/批准人保留。
4. **审计日志**：事件中文标签＋"任务#n · 动作#m · actor"元信息行＋ detail 摘要（paramsSummary 风格），原始 JSON 折叠在 <details>。

## 七、诚实边界

- 所有数字/状态来自真实 API/SSE；演示数据即后端种子数据，不编造。
- 未做真人点击验证（headless 截屏验收代替）；Cmd+K、口令 popover、折叠交互以构建通过＋截屏为准。
