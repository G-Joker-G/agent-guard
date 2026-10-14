import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, ShieldCheck, ShieldAlert } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { formatTime } from '../labels'
import { EventBadge, eventLabelOf } from '../components/status'
import { PageHeader, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Select } from '../components/ui/input'
import { Badge } from '../components/ui/badge'
import { Alert, AlertDescription } from '../components/ui/alert'

// detail 摘要：挑关键字段人类可读，而不是 raw JSON 直 dump
// 注意：后端 audit 表的 detail 列存的是 JSON 字符串，先 parse 再摘要
function parseDetail(d) {
  if (d == null || d === '') return null
  if (typeof d === 'object') return d
  if (typeof d === 'string') {
    try { return JSON.parse(d) } catch { return d.slice(0, 200) }
  }
  return String(d)
}

function detailSummary(e) {
  const d = parseDetail(e.detail)
  if (d == null) return null
  if (typeof d === 'string') return d
  const bits = []
  const RISK_CN = { low: '低风险', medium: '中风险', high: '高风险' }
  const DECISION_CN = { allow: '放行', needs_approval: '需审批', deny: '拒绝' }
  if (d.tool) bits.push(d.tool)
  if (d.decision) bits.push(`判定=${DECISION_CN[d.decision] || d.decision}`)
  if (d.reason) bits.push(d.reason)
  if (d.risk) bits.push(`风险=${RISK_CN[d.risk] || d.risk}`)
  if (d.origin) bits.push(`来源=${d.origin}`)
  if (d.thought) bits.push(String(d.thought).slice(0, 140))
  if (d.result && typeof d.result === 'object') {
    const r = d.result
    if (r.error) bits.push(`错误：${r.error}`)
    else if (r.to) bits.push(`收件人 ${r.to}`)
    else if (r.name) bits.push(`${r.name}`)
  }
  return bits.length ? bits.join(' · ') : null
}

export function AuditPage({ refreshKey }) {
  const [events, setEvents] = useState([])
  const [tasks, setTasks] = useState([])
  const [taskFilter, setTaskFilter] = useState('')
  const [verify, setVerify] = useState(null)
  const [error, setError] = useState('')

  const loadTasks = useCallback(async () => {
    try { setTasks(await api.listTasks()) } catch { /* 忽略，筛选可选 */ }
  }, [])

  const load = useCallback(async () => {
    try {
      const ev = await api.auditList(taskFilter ? Number(taskFilter) : undefined)
      setEvents(Array.isArray(ev) ? ev : ev.events || [])
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
  }, [taskFilter])

  const check = useCallback(async () => {
    try {
      const r = await api.auditVerify()
      setVerify({ ok: r.ok, checked: r.checked, at: new Date() })
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { loadTasks() }, [loadTasks])
  useEffect(() => { load(); check() }, [load, check, refreshKey])

  return (
    <div>
      <PageHeader
        title="审计日志"
        desc="审计即事件源：每条记录带哈希链，篡改可检出。"
        actions={
          <div className="flex items-center gap-2">
            {verify ? (
              verify.ok ? (
                <Badge variant="success" className="gap-1">
                  <ShieldCheck size={13} /> 哈希链校验通过（{verify.checked} 条）
                </Badge>
              ) : (
                <Badge variant="destructive" className="gap-1">
                  <ShieldAlert size={13} /> 哈希链校验失败
                </Badge>
              )
            ) : (
              <Badge variant="muted">校验中…</Badge>
            )}
            <Button variant="outline" size="sm" onClick={check}>重新校验</Button>
          </div>
        }
      />

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">按任务筛选</span>
            <Select value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)} className="w-56">
              <option value="">全部任务</option>
              {tasks.map((t) => <option key={t.id} value={t.id}>#{t.id} {t.title}</option>)}
            </Select>
            <Button variant="outline" size="sm" onClick={load}><RefreshCw size={14} /> 刷新</Button>
            <span className="tnum ml-auto text-xs text-muted-foreground">共 {events.length} 条</span>
          </div>
        </CardHeader>
        <CardContent>
          {events.length === 0 ? (
            <EmptyState title="暂无审计事件" desc="创建任务或运行演示后，审计事件会出现在这里。" />
          ) : (
            <ul className="space-y-1">
              {events.map((e) => {
                const summary = detailSummary(e)
                return (
                  <li key={e.id} className="flex gap-3 rounded-md px-2 py-2.5 hover:bg-muted/40">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-muted-foreground/40" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <EventBadge event={e.event} />
                        <span className="tnum text-xs text-muted-foreground">{formatTime(e.ts)}</span>
                        {e.task_id && <span className="font-mono text-xs text-muted-foreground">任务 #{e.task_id}</span>}
                        {e.action_id && <span className="font-mono text-xs text-muted-foreground">动作 #{e.action_id}</span>}
                        {e.actor && e.actor !== 'gateway' && (
                          <span className="text-xs text-muted-foreground">（{e.actor}）</span>
                        )}
                      </div>
                      {summary && (
                        <div className="mt-1 truncate text-sm text-muted-foreground">{summary}</div>
                      )}
                      {e.detail != null && e.detail !== '' && (
                        <details className="audit-detail mt-1">
                          <summary>原始记录</summary>
                          <pre>{typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail, null, 2)}</pre>
                        </details>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
