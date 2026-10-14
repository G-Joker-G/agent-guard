import { useEffect } from 'react'
import {
  LayoutDashboard, Activity, ClipboardList, ShieldCheck, ScrollText,
  Database, FlaskConical, OctagonX, RotateCcw, Plus, RefreshCw,
} from 'lucide-react'
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty,
  CommandGroup, CommandItem,
} from './ui/command'

// 全局命令面板：任何功能 3 次操作内可达。⌘K / Ctrl+K 唤起，Esc 关闭。
export function CommandPalette({
  open, onOpenChange, onNav, stopped, busy, onStop, onResume, onReset,
}) {
  useEffect(() => {
    const down = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        onOpenChange(!open)
      }
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [open, onOpenChange])

  const go = (key) => { onNav(key); onOpenChange(false) }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="搜索页面、操作…（如：审批、急停、演示）" />
      <CommandList>
        <CommandEmpty>没有匹配项</CommandEmpty>
        <CommandGroup heading="页面">
          <CommandItem onSelect={() => go('dashboard')}><LayoutDashboard />总览 Dashboard</CommandItem>
          <CommandItem onSelect={() => go('live')}><Activity />实时运行</CommandItem>
          <CommandItem onSelect={() => go('tasks')}><ClipboardList />任务中心</CommandItem>
          <CommandItem onSelect={() => go('approvals')}><ShieldCheck />审批中心</CommandItem>
          <CommandItem onSelect={() => go('audit')}><ScrollText />审计日志</CommandItem>
          <CommandItem onSelect={() => go('customers')}><Database />客户数据</CommandItem>
          <CommandItem onSelect={() => go('outbox')}><Database />发件箱</CommandItem>
          <CommandItem onSelect={() => go('demo')}><FlaskConical />演示</CommandItem>
        </CommandGroup>
        <CommandGroup heading="快捷操作">
          <CommandItem onSelect={() => go('tasks')}><Plus />新建任务（去任务中心）</CommandItem>
          {!stopped ? (
            <CommandItem disabled={busy} onSelect={() => { onOpenChange(false); onStop() }}>
              <OctagonX />紧急停止
            </CommandItem>
          ) : (
            <CommandItem disabled={busy} onSelect={() => { onOpenChange(false); onResume() }}>
              <RotateCcw />解除紧急停止
            </CommandItem>
          )}
          <CommandItem onSelect={() => go('demo')}><RefreshCw />一键重置演示数据（去演示页）</CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
