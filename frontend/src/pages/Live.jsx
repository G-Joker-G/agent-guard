import { useEffect, useState, useRef, useCallback } from 'react'
import { Play, Zap, StepForward, Cpu, FlaskConical, Activity } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { ActionBadge, TaskBadge, DecisionBadge, OriginBadge, EventBadge, eventLabelOf } from '../components/status'
import { VerdictPipeline } from '../components/pipeline'
import { PageHeader, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Badge } from '../components/ui/badge'
import { Alert, AlertDescription } from '../components/ui/alert'
import { paramsSummary, formatTime } from '../labels'

// 实时事件流：EventSource 订阅 /api/events（事件源 = 审计表）
// 后端帧无 id 字段、?since= 在挂载时固定，浏览器原生重连会全量重播事件。
// 这里按事件 id 去重（seenRef），重播的事件直接丢弃，避免时间线重复和 loadTaskDetail 请求风暴。
function useEventStream(onEvent, streamKey, onSse) {
  const [connected, setConnected] = useState(false)
  const lastIdRef = useRef(0)
  const seenRef = useRef(new Set())
  const cbRef = useRef(onEvent)
  cbRef.current = onEvent
  useEffect(() => {
    // 切换任务（streamKey 变化）时清空去重集合，避免旧事件 id 污染新任务时间线
    seenRef.current = new Set()
  }, [streamKey])
  useEffect(() => {
    const es = new EventSource(`/api/events?since=${lastIdRef.current}`)
    es.onopen = () => { setConnected(true); onSse && onSse(true) }
    es.onerror = () => { setConnected(false); onSse && onSse(false) }
    es.onmessage = (m) => {
      if (!m.data) return
      try {
        const e = JSON.parse(m.data)
        if (typeof e.id !== 'number') return
        if (seenRef.current.has(e.id)) return  // 重连重播，去重
        seenRef.current.add(e.id)
        if (seenRef.current.size > 1200) {
          seenRef.current = new Set([...seenRef.current].slice(-800))
        }
        if (e.id > lastIdRef.current) lastIdRef.current = e.id
        cbRef.current && cbRef.current(e)
      } catch { /* 忽略解析失败 */ }
    }
    return () => es.close()
  }, [])
  return connected
}

const SCENARIOS = [
  { key: 'followup', label: '客户跟进', title: '实时演示 · 客户跟进' },
  { key: 'export_attack', label: '越权攻击', title: '实时演示 · 越权攻击' },
  { key: 'batch', label: '批量操作', title: '实时演示 · 批量操作' },
]

function resultSummary(result) {
  if (!result) return null
  if (result.error) return `错误：${result.error}`
  const bits = []
  if (result.to) bits.push(`收件人 ${result.to}`)
  if (result.subject) bits.push(`主题「${result.subject}」`)
  if (result.outbox_id) bits.push(`发件箱 #${result.outbox_id}`)
  if (result.updated) bits.push(`更新字段：${Object.keys(result.updated).join('、')}`)
  if (result.name) bits.push(`${result.name}（${result.company || ''}）`)
  return bits.length ? bits.join('；') : JSON.stringify(result).slice(0, 120)
}

export function LivePage({ onSse }) {
  const [tasks, setTasks] = useState([])
  const [taskId, setTaskId] = useState(null)
  const [task, setTask] = useState(null)
  const [events, setEvents] = useState([])
  const [pending, setPending] = useState([])
  const [goal, setGoal] = useState('跟进客户 1：先读取客户资料，然后发送产品白皮书邮件')
  const [llm, setLlm] = useState(null)
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [approver, setApprover] = useState('admin')
  const bottomRef = useRef(null)

  const loadTasks = useCallback(async () => {
    try {
      const list = await api.listTasks()
      setTasks(list)
      if (!taskId && list.length) setTaskId(list[0].id)
    } catch { /* 静默 */ }
  }, [taskId])

  const loadTaskDetail = useCallback(async (id) => {
    if (!id) return
    try {
      const [t, p] = await Promise.all([
        api.getTask(id),
        api.pendingApprovals().catch(() => []),
      ])
      setTask(t)
      setPending(Array.isArray(p) ? p : [])
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  const loadLlm = useCallback(async () => {
    try { setLlm(await api.llmStatus()) } catch { setLlm(null) }
  }, [])

  useEffect(() => { loadTasks(); loadLlm() }, [loadTasks, loadLlm])
  useEffect(() => {
    if (!taskId) return
    setEvents([])
    loadTaskDetail(taskId)
  }, [taskId, loadTaskDetail])

  const connected = useEventStream(useCallback((e) => {
    if (e.task_id !== taskId) return
    setEvents((evs) => [...evs.slice(-400), e])
    loadTaskDetail(taskId)
  }, [taskId, loadTaskDetail]), taskId, onSse)

  useEffect(() => {
    bottomRef.current && bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [events.length])

  async function newTask(scenario, title) {
    setBusy(true)
    try {
      const t = await api.createTask(title, scenario)
      await loadTasks()
      setTaskId(t.id)
      setError('')
      return t
    } catch (e) { setError(apiErrorMessage(e)); return null }
    finally { setBusy(false) }
  }

  // 演示 Agent 运行：plan → advance（V1 语义；遇审批停下，人工在卡片上决策后点"继续推进"）
  async function runDemoAgent() {
    if (running) return
    setRunning(true)
    try {
      const t = await newTask('followup', '实时演示 · 客户跟进（演示 Agent）')
      if (!t) return
      await api.planTask(t.id)
      await api.advanceTask(t.id)
      await loadTaskDetail(t.id)
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setRunning(false) }
  }

  async function runAttackDemo() {
    if (running) return
    setRunning(true)
    try {
      const t = await newTask('export_attack', '实时演示 · 越权攻击（演示 Agent）')
      if (!t) return
      await api.planTask(t.id)
      await api.advanceTask(t.id)
      await loadTaskDetail(t.id)
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setRunning(false) }
  }

  async function advance() {
    if (!taskId || busy) return
    setBusy(true)
    try { await api.advanceTask(taskId); await loadTaskDetail(taskId); setError('') }
    catch (e) { setError(apiErrorMessage(e)) }
    finally { setBusy(false) }
  }

  async function executeAction(id) {
    setBusy(true)
    try { await api.executeAction(id); await loadTaskDetail(taskId); setError('') }
    catch (e) { setError(apiErrorMessage(e)) }
    finally { setBusy(false) }
  }

  async function decide(approvalId, decision) {
    setBusy(true)
    try {
      await api.decideApproval(approvalId, decision, approver || 'admin', '实时运行页决策')
      await loadTaskDetail(taskId)
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setBusy(false) }
  }

  async function runLlm() {
    if (!taskId || running) return
    setRunning(true)
    try {
      await api.runLlm(taskId, goal)
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setRunning(false) }
  }

  const approvalByAction = {}
  pending.forEach((a) => { approvalByAction[a.action_id] = a })
  const actions = (task && task.actions) || []
  const steps = events.filter((e) => e.event === 'agent.step')

  return (
    <div>
      <PageHeader
        title="实时运行"
        desc="Agent 推理步骤 → 工具请求（网关裁决流水线）→ 待审批可直接决策 → 执行结果。右侧为实时审计时间线。"
        actions={
          <Badge variant={connected ? 'success' : 'warning'}>
            {connected ? '事件流已连接' : '事件流连接中…'}
          </Badge>
        }
      />

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* 场景启动器：所有"开始"类操作收拢到一张卡片，按主/次/危险分级 */}
      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><FlaskConical size={16} />场景启动器</CardTitle>
          <CardDescription>选择任务，或一键启动演示场景。演示 Agent 为确定性模拟，非真实 LLM 推理。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">任务</span>
            <select
              value={taskId || ''}
              onChange={(e) => setTaskId(Number(e.target.value) || null)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="">— 选择任务 —</option>
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>#{t.id} {t.title}</option>
              ))}
            </select>
            <span className="mx-1 h-5 w-px bg-border" />
            {SCENARIOS.map((s) => (
              <Button key={s.key} variant="outline" size="sm" disabled={busy || running}
                onClick={() => newTask(s.key, s.title)}>
                新建·{s.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={busy || running} onClick={runDemoAgent}>
              <Play size={15} /> 演示 Agent 运行（跟进）
            </Button>
            <Button variant="destructive" disabled={busy || running} onClick={runAttackDemo}>
              <Zap size={15} /> 演示攻击拦截（越权）
            </Button>
            <Button variant="secondary" disabled={busy || running || !taskId} onClick={advance}>
              <StepForward size={15} /> 继续推进
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <Cpu size={15} className="text-muted-foreground" />
            <Input
              type="text" value={goal} onChange={(e) => setGoal(e.target.value)}
              placeholder="给真实 LLM 的任务目标" className="min-w-60 flex-1"
            />
            <Button
              variant="secondary" disabled={busy || running || !taskId || !llm?.configured}
              onClick={runLlm} title={llm?.configured ? '' : '未配置 LLM_API_KEY'}
            >
              真实 LLM 运行
            </Button>
            <span className="w-full text-xs text-muted-foreground">
              {llm === null ? 'LLM 状态未知' : llm.configured
                ? `已配置：${llm.model} · 今日调用 ${llm.daily_calls_used ?? '—'}/${llm.daily_calls_limit ?? '—'}${llm.kill_switch ? ' · 熔断已开启' : ''}`
                : '未配置 LLM_API_KEY（仅演示模式可用；验收时在 .env 中配置）'}
            </span>
          </div>
        </CardContent>
      </Card>

      {!task ? (
        <EmptyState
          icon={Activity} title="请选择或新建一个任务开始"
          desc="用场景启动器一键运行演示，或在任务中心创建任务。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
          <div className="xl:col-span-3">
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  任务 #{task.id} · {task.title} <TaskBadge status={task.status} />
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {steps.length > 0 && (
                  <div>
                    <div className="mb-2 text-sm font-medium">Agent 推理步骤</div>
                    <div className="space-y-2">
                      {steps.map((s) => (
                        <div key={s.id} className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                          <div className="font-mono text-xs text-muted-foreground">
                            步骤 {s.detail?.step ?? '—'} · {formatTime(s.ts)}
                          </div>
                          <div className="mt-0.5">{s.detail?.thought || JSON.stringify(s.detail)}</div>
                          {s.detail?.tool_calls && (
                            <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                              → 调用：{s.detail.tool_calls.join('、')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <div className="mb-2 text-sm font-medium">工具请求（{actions.length}）</div>
                  {actions.length === 0 ? (
                    <EmptyState title="暂无动作" desc="先运行演示 Agent 或真实 LLM。" />
                  ) : (
                    <div className="space-y-3">
                      {actions.map((a) => {
                        const ap = approvalByAction[a.id]
                        return (
                          <div key={a.id} className="rounded-lg border border-border bg-muted/20 p-4">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="tnum font-mono text-sm font-semibold">#{a.seq}</span>
                              <span className="font-mono text-sm">{a.tool}</span>
                              <OriginBadge origin={a.origin} />
                              <ActionBadge status={a.status} />
                            </div>
                            <div className="mt-2">
                              <VerdictPipeline action={a} />
                            </div>
                            <div className="mt-2 text-sm text-muted-foreground">{paramsSummary(a.params)}</div>
                            {a.decision && (
                              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                                <span className="text-muted-foreground">网关判定</span>
                                <DecisionBadge decision={a.decision} />
                                {a.decision_reason && (
                                  <span className="text-muted-foreground">{a.decision_reason}</span>
                                )}
                              </div>
                            )}
                            {a.status === 'needs_approval' && (
                              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                                {ap ? (
                                  <>
                                    <Button size="sm" variant="success" disabled={busy}
                                      onClick={() => decide(ap.id, 'approve')}>批准执行</Button>
                                    <Button size="sm" variant="destructive" disabled={busy}
                                      onClick={() => decide(ap.id, 'reject')}>拒绝</Button>
                                    <span className="text-xs text-muted-foreground">
                                      审批单 #{ap.id} · 批准人：
                                    </span>
                                    <Input
                                      type="text" value={approver}
                                      onChange={(e) => setApprover(e.target.value)}
                                      className="h-8 w-24"
                                    />
                                  </>
                                ) : <span className="text-xs text-muted-foreground">审批单同步中…</span>}
                              </div>
                            )}
                            {a.status === 'approved' && (
                              <div className="mt-3 border-t border-border pt-3">
                                <Button size="sm" disabled={busy} onClick={() => executeAction(a.id)}>
                                  执行（网关复查审批绑定）
                                </Button>
                              </div>
                            )}
                            {a.result && (
                              <div className="mt-2 rounded-md bg-muted/40 px-3 py-2 text-sm">
                                <span className="text-muted-foreground">执行结果：</span>{resultSummary(a.result)}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
          <div className="xl:col-span-2">
            <Card className="xl:sticky xl:top-24">
              <CardHeader>
                <CardTitle>实时审计时间线</CardTitle>
                <CardDescription>事件源即审计表，所见即审计。</CardDescription>
              </CardHeader>
              <CardContent>
                {events.length === 0 ? (
                  <EmptyState title="等待事件…" desc="运行演示或推进任务后，事件会实时出现在这里。" />
                ) : (
                  <ul className="max-h-[560px] space-y-3 overflow-y-auto pr-1">
                    {[...events].reverse().map((e) => (
                      <li key={e.id} className="flex gap-2.5">
                        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary/70" />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <EventBadge event={e.event} />
                            <span className="tnum text-xs text-muted-foreground">{formatTime(e.ts)}</span>
                          </div>
                          {e.action_id && <div className="mt-0.5 font-mono text-xs text-muted-foreground">动作 #{e.action_id}</div>}
                          {e.event === 'action.policy' && e.detail && (
                            <div className="mt-0.5 text-xs text-muted-foreground">
                              {e.detail.tool} → {e.detail.decision}：{e.detail.reason}
                            </div>
                          )}
                          {e.event === 'agent.step' && e.detail?.thought && (
                            <div className="mt-0.5 truncate text-xs text-muted-foreground">
                              {String(e.detail.thought).slice(0, 160)}
                            </div>
                          )}
                        </div>
                      </li>
                    ))}
                    <div ref={bottomRef} />
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
