# Agent Guard 前端 UI 重设计报告（UI_REDESIGN）

> 任务书：专业级 UI/UX 重设计 · 工具：Impeccable skill（项目内 `.impeccable/`）+ shadcn/ui（JSX）+ Tailwind CSS v4
> 设计规范全文见 `docs/DESIGN_SPEC.md`；产品上下文见 `PRODUCT.md`

## 一、设计问题审计清单（2026-10-14，headless Chromium 逐页截屏）

1. 窄栏居中：所有页面挤在 ~1100px 居中列，两侧大片黑空地。
2. 顶部噪音：蓝色小字横幅占一整行；header 里品牌＋7 个平铺导航按钮＋状态文字＋口令输入框＋紧急停止挤在一行。
3. 导航无分组：7 个 Tab 平铺，"找按钮难"的根源；审批计数藏在按钮文字里。
4. 说明书式文案：实时运行页一大段使用说明。
5. 按钮散落三处：新建场景×3／演示运行×2＋继续推进／目标输入＋真实 LLM 运行，样式不统一。
6. 信息冗余：工具卡片"网关判定：放行 只读客户信息，低风险 风险：low"。
7. 审计日志 = JSON 直 dump，可读性差。
8. 空态占半屏：实时时间线"等待事件…"。
9. 无总览 Dashboard。
10. 无统一设计语言：黑底＋默认蓝按钮。

审计截图：`/tmp/shot/before_*.png`（7 张，审计用，已保留在截屏机）

## 二、设计决策

- **信息架构先行**：侧边栏分组导航（监控／管控／数据／系统），操作按钮收敛到固定位置（页头右侧主操作＋表格行内），危险操作（急停／拒绝）永远固定位置＋红色。
- **新增总览 Dashboard**：4 张状态卡（网关状态／待审批／任务总数／今日 LLM 调用 x/50）＋待审批快捷＋最近审计事件——全部来自真实 API。
- **签名手法**：网关裁决流水线（提议 → 网关裁决 → 审批 → 执行），颜色即状态，用在工具请求卡片与任务详情。这是产品机制的可视化。
- **Cmd+K 全局命令面板**：任何功能 3 次操作内可达，专治"按钮难找"。
- **审计时间线重做**：中文事件标签＋关键字段摘要，原始 JSON 折叠。
- **深色模式**：近黑蓝调底＋一支主蓝＋语义色只做状态信使；无渐变字／玻璃拟态／装饰网格。

## 三、改了什么（文件级）

- 新增：`src/pages/Dashboard.jsx`（总览）、`src/components/layout.jsx`（AppShell 侧边栏＋顶栏、PageHeader、Stat、EmptyState）、`src/components/status.jsx`（状态→语义色唯一映射）、`src/components/pipeline.jsx`（裁决流水线）、`src/components/palette.jsx`（⌘K）
- 重写：`src/App.jsx`（新外壳；数据逻辑原样）、`src/pages/Live.jsx`、`Tasks.jsx`、`Approvals.jsx`、`Audit.jsx`、`Data.jsx`、`Demo.jsx`（数据逻辑与 API 调用原样，只换皮肤与布局）
- 基建：`vite.config.js` 接入 `@tailwindcss/vite`（旧 agent 装了包但没接插件）；`main.jsx` 改引 `index.css`；`index.css` 补滚动条／选区／审计折叠／流水线样式
- 删除：`src/components.jsx`、`src/styles.css`（旧手写 CSS，已无引用）
- 文档：`docs/DESIGN_SPEC.md`（设计规范）、`PRODUCT.md`（Impeccable 产品上下文）、`.impeccable/surfaces/`（surface brief）
- `.gitignore` 加 `.impeccable/`（3906 文件的 skill 工具链，不进仓库）
- **未动**：后端全部代码、所有 API 契约、安全／权限／审批／审计逻辑、SSE 语义

## 四、验收证据

- headless Chromium 逐页截屏（新）：`/tmp/shot/after_*.png`＋`/tmp/shot/fix_*.png`（8＋8 张）
  - 总览／实时运行（含裁决流水线）／任务中心／审批中心／审计日志（摘要＋折叠）／数据管理（客户＋发件箱）／演示
- 发现并修复 3 处：审计 detail 摘要未 parse JSON 字符串（曾直出 raw JSON）；顶栏事件流指示器在非 live 页误报"连接中"；Live 卡片风险徽章与判定理由文字重复
- Impeccable 机械检测：`impeccable detect` 对全部改动文件 0 findings

## 五、测试证据（云电脑亲自跑过）

- `npm run build` → 通过
- `pytest backend/tests/ -q` → **44 passed**（重设计未动后端，回归确认）
- `scripts/demo_e2e.py` → A/B/C 全绿

## 六、诚实未验证项

- 真人点击验证（Cmd+K 开合、口令输入、折叠交互、流水线各状态）未做——以构建通过＋截屏为准
- 真实 key 的场景 A、Docker Compose、start-mac.sh 的 macOS 实测（与本次无关，沿用之前口径）

## 七、本地预览方式

```bash
# 后端（已在本机 127.0.0.1:8000 运行）
cd ~/workspace/agent-guard/backend && venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 前端（已在本机 127.0.0.1:5173 运行，Tailwind v4 dev 模式）
cd ~/workspace/agent-guard/frontend && npx vite --host 127.0.0.1 --port 5173
# 用户在自己电脑：cd frontend && npm install && npm run dev（默认 http://localhost:5173，代理 /api → localhost:8000）
```

## 九、视觉转向：浅色清爽风（2026-10-14，用户反馈"太沉闷极客，要清爽"）

**转向原因**：上一版深色"深夜运维中心"方向被用户否决——太丑、太沉闷极客。信息架构（分组导航、按钮收敛、总览 Dashboard、Cmd+K、审计时间线、急停固定位置）未被否定，保留；只重做视觉层。

**视觉决策**（Impeccable colorize 流程：roles 而非 swatches）：
1. 默认浅色：`#f7f8fa` 极浅灰画布 + 白色卡片 + `#e7e9ed` 细边框 + `shadow-sm` 轻阴影，大量留白。
2. 一支克制主蓝 `#2563eb`（禁用霓虹感）；导航激活态为淡蓝底 `#e8eefc` + 主蓝文字。
3. 语义色降饱和度但保对比度：徽章统一为 15% 淡底 + 600 系文字（绿 #16a34a / 琥珀 #d97706 / 天蓝 #0284c7 / 红 #dc2626）。
4. 排版更轻：行高 1.65，选区/滚动条/代码块全部浅色化；审计时间线圆点加深到 `muted-foreground/40`（原 `bg-border` 在浅色下几乎看不见）。
5. 深色模式保留顶栏切换入口（默认浅色，localStorage 持久化）；深色 token 与浅色各自成稿、非机械反转。
6. 主题实现：Tailwind v4 `@theme inline` 把 `--color-*` 映射到运行时变量，`:root` 放浅色、`.dark` 覆盖深色。

**改动文件**：`src/index.css`（主题重写）、`src/components/layout.jsx`（侧边栏去硬编码深色、主题切换按钮、激活态减淡）、`src/App.jsx`（主题 state）、`src/components/ui/dialog.jsx`（遮罩 `bg-black/70`→`/45`）、`src/pages/Audit.jsx`（时间线圆点）。

**验收**：headless Chromium 逐页截屏 6 张（`docs/preview/*-light.png`）：总览／实时运行／任务中心／审批中心／审计日志／数据管理；深色回归截屏 1 张确认未破坏。结论：沉闷感消除，留白/层级/语义色均达标。

## 八、版本

- 本地 commits（未推送远端，远端 main 保持 `db805d7` 验收基线不动）：
  - `fe50ff0` design: 浅色清爽主题返工（本次：默认浅色 + 深色切换保留）
  - `c3aeaf5` design: shadcn/ui 重设计控制台（信息架构重组）
  - 之前：`3ec6fe2`、`c5b4dd2`（成本熔断＋安全加固）
- 本机 clone 未配置 remote（`git remote -v` 为空），无推送可能
