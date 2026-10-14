import {
  LayoutDashboard, Activity, ClipboardList, ShieldCheck, ScrollText,
  Database, FlaskConical, OctagonX, Search, Lock, Radio, RotateCcw, Sun, Moon,
} from 'lucide-react'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { Input } from './ui/input'
import { Card, CardContent } from './ui/card'
import { cn } from '../lib/utils'

// 导航分组：监控 / 管控 / 数据 / 系统
export const NAV_GROUPS = [
  {
    title: '监控',
    items: [
      { key: 'dashboard', label: '总览', icon: LayoutDashboard },
      { key: 'live', label: '实时运行', icon: Activity },
    ],
  },
  {
    title: '管控',
    items: [
      { key: 'tasks', label: '任务中心', icon: ClipboardList },
      { key: 'approvals', label: '审批中心', icon: ShieldCheck, badge: 'pendingCount' },
      { key: 'audit', label: '审计日志', icon: ScrollText },
    ],
  },
  {
    title: '数据',
    items: [{ key: 'data', label: '数据管理', icon: Database }],
  },
  {
    title: '系统',
    items: [{ key: 'demo', label: '演示', icon: FlaskConical }],
  },
]

export function AppShell({
  tab, onNav, pendingCount, stopped, busy, onStop, onResume,
  adminToken, onAdminToken, connectionOk, showConnection, onOpenPalette,
  theme, onToggleTheme, children,
}) {
  return (
    <div className="flex min-h-screen">
      {/* 侧边栏 */}
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-border bg-card">
        <div className="flex h-16 items-center gap-2.5 border-b border-border px-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="h-4.5 w-4.5" size={18} />
          </span>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">Agent Guard</div>
            <div className="text-[11px] text-muted-foreground">执行控制层</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {NAV_GROUPS.map((g) => (
            <div key={g.title} className="mb-5">
              <div className="mb-1.5 px-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/70">
                {g.title}
              </div>
              {g.items.map((item) => {
                const Icon = item.icon
                const active = tab === item.key || (item.key === 'data' && (tab === 'customers' || tab === 'outbox'))
                const count = item.badge === 'pendingCount' ? pendingCount : 0
                return (
                  <button
                    key={item.key}
                    onClick={() => onNav(item.key)}
                    className={cn(
                      'mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                      active
                        ? 'bg-primary/10 font-medium text-primary'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                    )}
                  >
                    <Icon size={17} className="shrink-0" />
                    <span className="flex-1 text-left">{item.label}</span>
                    {count > 0 && (
                      <Badge variant="warning" className="tnum px-1.5">{count}</Badge>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <div className={cn(
            'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs',
            stopped ? 'border-destructive/50 bg-destructive/10 text-destructive'
              : 'border-border bg-muted/40 text-muted-foreground',
          )}>
            <span className={cn('h-2 w-2 rounded-full', stopped ? 'bg-destructive' : 'bg-success')} />
            {stopped ? '紧急停止已生效' : '网关运行中'}
          </div>
        </div>
      </aside>

      {/* 主区 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏：标题 ｜ 搜索 ｜ 状态 ｜ 口令 ｜ 急停（永远右端、永远红色） */}
        <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-border bg-background/95 px-6 backdrop-blur">
          <button
            onClick={onOpenPalette}
            className="flex h-9 w-64 items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Search size={15} />
            <span className="flex-1 text-left">搜索功能、页面…</span>
            <kbd className="rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
          </button>
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleTheme}
            title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            className="text-muted-foreground"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </Button>
          {showConnection && (
            <span className={cn(
              'flex items-center gap-1.5 text-xs',
              connectionOk ? 'text-muted-foreground' : 'text-warning',
            )}>
              <Radio size={13} className={connectionOk ? 'text-success' : 'text-warning'} />
              {connectionOk ? '事件流已连接' : '事件流连接中'}
            </span>
          )}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground" title="后端 .env 设置 GUARD_ADMIN_TOKEN 后，在此填入口令，管理/审批请求会自动携带">
            <Lock size={13} />
            <Input
              type="password"
              value={adminToken}
              onChange={(e) => onAdminToken(e.target.value)}
              placeholder="管理口令（未设则留空）"
              className="h-8 w-40"
            />
          </div>
          {!stopped ? (
            <Button variant="destructive" size="sm" disabled={busy} onClick={onStop} className="gap-1.5 font-semibold">
              <OctagonX size={15} /> 紧急停止
            </Button>
          ) : (
            <Button variant="success" size="sm" disabled={busy} onClick={onResume} className="gap-1.5 font-semibold">
              <RotateCcw size={15} /> 解除急停
            </Button>
          )}
        </header>
        <main className="min-w-0 flex-1 p-6 lg:p-8">
          {children}
          <footer className="mt-10 border-t border-border pt-4 text-center text-xs text-muted-foreground/70">
            Agent Guard V2 · 所有权限判定均由后端网关作出，前端仅做展示 · 审计即事件源
          </footer>
        </main>
      </div>
    </div>
  )
}

export function PageHeader({ title, desc, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {desc && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{desc}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Stat({ icon: Icon, label, value, sub, tone }) {
  const tones = {
    default: 'text-foreground', danger: 'text-destructive',
    warn: 'text-warning', ok: 'text-success', info: 'text-primary',
  }
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        {Icon && (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
            <Icon size={19} className={tones[tone] || tones.default} />
          </span>
        )}
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className={cn('tnum mt-0.5 truncate text-2xl font-semibold tracking-tight', tones[tone] || tones.default)}>
            {value}
          </div>
          {sub && <div className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  )
}

export function EmptyState({ icon: Icon, title, desc, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 px-6 py-12 text-center">
      {Icon && <Icon size={28} className="mb-3 text-muted-foreground/60" />}
      <div className="text-sm font-medium">{title}</div>
      {desc && <div className="mt-1 max-w-sm text-xs text-muted-foreground">{desc}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
