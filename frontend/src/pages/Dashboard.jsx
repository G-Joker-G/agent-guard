import { useEffect, useState, useCallback } from 'react'
import { ShieldCheck, ClipboardList, Cpu, Activity, Inbox, ArrowRight } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { PageHeader, Stat, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { TaskBadge, EventBadge, eventLabelOf } from '../components/status'
import { formatTime, paramsSummary } from '../labels'

// 总览 Dashboard：先看到"系统是否安全、有什么等我处理"。
// 所有数字均来自真实 API，不编造。
export function DashboardPage({ onNav, onOpenTask, refreshKey }) {
  const [stopped, setStopped] = useState(false)
  const [pending, setPending] = useState([])
  const [tasks, setTasks] = useState([])
  const [llm, setLlm] = useState(null)
  const [events, setEvents] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [s, p, t, l, ev] = await Promise.all([
        api.status().catch(() => null),
        api.pendingApprovals().catch(() => []),
        api.listTasks().catch(() => []),
        api.llmStatus().catch(() => null),
        api.auditList(undefined, 8).catch(() => []),
      ])
      if (s) setStopped(!!s.emergency_stop)
      setPending(Array.isArray(p) ? p : [])
      setTasks(Array.isArray(t) ? t : [])
      setLlm(l)
      const list = Array.isArray(ev) ? ev : ev.events || []
      setEvents(list.slice(0, 8))
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  const llmText = llm === null ? '未知'
    : llm.kill_switch ? '熔断开启'
    : `${llm.daily_calls_used ?? '—'}/${llm.daily_calls_limit ?? '—'}`

  return (
    <div>
      <PageHeader
        title="总览"
        desc="系统安全状态与待办事项。所有判定由后端网关作出，这里只做呈现。"
      />

      {error && <div className="mb-4 text-sm text-destructive">{error}</div>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          icon={ShieldCheck} label="网关状态"
          value={stopped ? '已急停' : '运行中'} tone={stopped ? 'danger' : 'ok'}
          sub={stopped ? '拒绝新动作与一切执行' : '正常裁决工具调用'}
        />
        <Stat
          icon={Inbox} label="待审批"
          value={String(pending.length)} tone={pending.length ? 'warn' : 'default'}
          sub={pending.length ? '需要人工决策' : '暂无待办'}
        />
        <Stat
          icon={ClipboardList} label="任务总数"
          value={String(tasks.length)} tone="default"
          sub={tasks.length ? `最近：#${tasks[tasks.length - 1].id}` : '尚未创建任务'}
        />
        <Stat
          icon={Cpu} label="今日 LLM 调用"
          value={llmText} tone={llm && llm.kill_switch ? 'danger' : 'default'}
          sub={llm ? (llm.configured ? llm.model : '未配置 key（演示模式）') : '—'}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>待审批事项</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => onNav('approvals')}>
              去审批中心 <ArrowRight size={14} />
            </Button>
          </CardHeader>
          <CardContent>
            {pending.length === 0 ? (
              <EmptyState title="暂无待审批事项" desc="新的敏感工具调用出现时，会在这里等待人工决策。" />
            ) : (
              <ul className="divide-y divide-border">
                {pending.slice(0, 5).map((a) => {
                  const act = a.action || {}
                  return (
                    <li key={a.id} className="flex items-center gap-3 py-2.5">
                      <span className="tnum font-mono text-xs text-muted-foreground">#{a.id}</span>
                      <span className="font-mono text-xs">{act.tool || a.tool || '—'}</span>
                      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                        {paramsSummary(act.params || a.params)}
                      </span>
                      <Button variant="outline" size="sm" onClick={() => onNav('approvals')}>去审批</Button>
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>最近审计事件</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => onNav('audit')}>
              查看全部 <ArrowRight size={14} />
            </Button>
          </CardHeader>
          <CardContent>
            {events.length === 0 ? (
              <EmptyState
                icon={Activity} title="暂无审计事件"
                desc="创建任务或运行演示后，这里的事件流会实时更新。"
                action={<Button size="sm" onClick={() => onNav('live')}>去实时运行</Button>}
              />
            ) : (
              <ul className="divide-y divide-border">
                {events.map((e) => (
                  <li key={e.id} className="flex items-center gap-3 py-2.5">
                    <EventBadge event={e.event} />
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                      {e.task_id ? `任务 #${e.task_id} · ` : ''}{eventLabelOf(e.event)}
                    </span>
                    <span className="tnum shrink-0 text-xs text-muted-foreground">{formatTime(e.ts)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {tasks.length > 0 && (
        <Card className="mt-4">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>最近任务</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => onNav('tasks')}>
              任务中心 <ArrowRight size={14} />
            </Button>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border">
              {[...tasks].slice(-5).reverse().map((t) => (
                <li key={t.id}>
                  <button onClick={() => onOpenTask(t.id)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-accent/40 rounded px-1 -mx-1">
                    <span className="tnum font-mono text-xs text-muted-foreground">#{t.id}</span>
                    <span className="min-w-0 flex-1 truncate text-sm">{t.title}</span>
                    <TaskBadge status={t.status} />
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
