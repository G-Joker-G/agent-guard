import { useEffect, useState, useRef, useCallback } from 'react'
import { api, apiErrorMessage } from '../api'
import { ActionBadge, TaskBadge, ErrorBox, Empty } from '../components'
import { paramsSummary, formatTime, DECISION_LABEL } from '../labels'

// 实时事件流：EventSource 订阅 /api/events（事件源 = 审计表）
function useEventStream(onEvent) {
  const [connected, setConnected] = useState(false)
  const lastIdRef = useRef(0)
  const cbRef = useRef(onEvent)
  cbRef.current = onEvent
  useEffect(() => {
    const es = new EventSource(`/api/events?since=${lastIdRef.current}`)
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.onmessage = (m) => {
      if (!m.data) return
      try {
        const e = JSON.parse(m.data)
        if (e.id > lastIdRef.current) lastIdRef.current = e.id
        cbRef.current && cbRef.current(e)
      } catch { /* 忽略解析失败 */ }
    }
    return () => es.close()
  }, [])
  return connected
}

const ORIGIN_LABEL = { web: '控制台', demo: '演示 Agent', mcp: 'MCP 客户端', llm: 'LLM Agent' }

const EVENT_LABEL = {
  'task.created': '任务创建',
  'action.proposed': 'Agent 提议动作',
  'action.policy': '网关策略评估',
  'approval.created': '审批单创建',
  'approval.approved': '审批通过',
  'approval.rejected': '审批驳回',
  'approval.timeout': '审批等待超时',
  'action.executed': '执行成功',
  'action.denied': '策略拒绝',
  'action.failed': '执行失败',
  'action.blocked_stop': '急停拦截',
  'action.execute_rejected': '执行被拒',
  'stop.engaged': '紧急停止',
  'stop.released': '解除急停',
  'data.reset': '数据重置',
  'agent.step': 'Agent 推理',
  'agent.error': 'Agent 出错',
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

export function LivePage() {
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
  }, [taskId, loadTaskDetail]))

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
      <div className="panel">
        <h2>实时运行 · 安全执行可视化
          <span className={`badge ${connected ? 'st-done' : 'st-waiting'}`} style={{ marginLeft: 10 }}>
            {connected ? '事件流已连接' : '事件流连接中…'}
          </span>
        </h2>
        <p className="muted">
          左侧：Agent 推理步骤 → 工具请求卡片（策略判定 + 原因）→ 待审批可直接批准/拒绝 → 执行结果。
          右侧：实时审计时间线。所有判定均由后端网关作出；事件源即审计表，保证"所见即审计"。
        </p>
        <div className="toolbar">
          <label>任务：
            <select value={taskId || ''} onChange={(e) => setTaskId(Number(e.target.value) || null)}>
              <option value="">— 选择任务 —</option>
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>#{t.id} {t.title}</option>
              ))}
            </select>
          </label>
          {SCENARIOS.map((s) => (
            <button key={s.key} className="btn small" disabled={busy || running}
              onClick={() => newTask(s.key, s.title)}>新建·{s.label}</button>
          ))}
        </div>
        <div className="toolbar">
          <button className="btn primary" disabled={busy || running} onClick={runDemoAgent}>
            演示 Agent 运行（跟进场景）
          </button>
          <button className="btn primary" disabled={busy || running} onClick={runAttackDemo}>
            演示攻击拦截（越权场景）
          </button>
          <button className="btn small" disabled={busy || !taskId} onClick={advance}>继续推进</button>
          <span className="muted">演示 Agent 为确定性模拟，非真实 LLM 推理。</span>
        </div>
        <div className="toolbar">
          <input type="text" value={goal} onChange={(e) => setGoal(e.target.value)}
            placeholder="给真实 LLM 的任务目标" style={{ flex: 1, minWidth: 240 }} />
          <button className="btn primary" disabled={busy || running || !taskId || !llm?.configured}
            onClick={runLlm} title={llm?.configured ? '' : '未配置 LLM_API_KEY'}>
            真实 LLM 运行
          </button>
          <span className="muted">
            {llm === null ? 'LLM 状态未知' : llm.configured
              ? `已配置：${llm.model}`
              : '未配置 LLM_API_KEY（仅演示模式可用；验收时在 .env 中配置）'}
          </span>
        </div>
        <ErrorBox error={error} onClose={() => setError('')} />
      </div>

      {!task ? <div className="panel"><Empty text="请选择或新建一个任务开始" /></div> : (
        <div className="live-grid">
          <div>
            <div className="panel">
              <h2>任务 #{task.id} · {task.title} <TaskBadge status={task.status} /></h2>
              {steps.length > 0 && (
                <div>
                  <h3>Agent 推理步骤</h3>
                  {steps.map((s) => (
                    <div className="step-card" key={s.id}>
                      <div className="mono muted">步骤 {s.detail?.step ?? '—'} · {formatTime(s.ts)}</div>
                      <div>{s.detail?.thought || JSON.stringify(s.detail)}</div>
                      {s.detail?.tool_calls && (
                        <div className="mono muted">→ 调用：{s.detail.tool_calls.join('、')}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <h3>工具请求</h3>
              {actions.length === 0 ? <Empty text="暂无动作：先运行演示 Agent 或真实 LLM" /> : actions.map((a) => {
                const ap = approvalByAction[a.id]
                return (
                  <div className="action-card" key={a.id}>
                    <div className="row">
                      <span className="mono"><strong>#{a.seq}</strong> {a.tool}</span>
                      <span className="origin-badge">{ORIGIN_LABEL[a.origin] || a.origin}</span>
                      <ActionBadge status={a.status} />
                    </div>
                    <div className="muted">{paramsSummary(a.params)}</div>
                    {a.decision && (
                      <div>
                        网关判定：<span className={`verdict v-${a.decision}`}>{DECISION_LABEL[a.decision] || a.decision}</span>
                        <span className="muted">　{a.decision_reason}</span>
                        {a.risk && <span className="muted">　风险：{a.risk}</span>}
                      </div>
                    )}
                    {a.status === 'needs_approval' && (
                      <div className="row" style={{ marginTop: 6 }}>
                        {ap ? (
                          <>
                            <button className="btn small ok" disabled={busy}
                              onClick={() => decide(ap.id, 'approve')}>批准执行</button>
                            <button className="btn small danger" disabled={busy} style={{ marginLeft: 6 }}
                              onClick={() => decide(ap.id, 'reject')}>拒绝</button>
                            <span className="muted">审批单 #{ap.id} · 批准人：
                              <input type="text" value={approver} onChange={(e) => setApprover(e.target.value)}
                                style={{ width: 90 }} /></span>
                          </>
                        ) : <span className="muted">审批单同步中…</span>}
                      </div>
                    )}
                    {a.status === 'approved' && (
                      <div className="row" style={{ marginTop: 6 }}>
                        <button className="btn small primary" disabled={busy}
                          onClick={() => executeAction(a.id)}>执行（网关复查审批绑定）</button>
                      </div>
                    )}
                    {a.result && (
                      <div className="result-line">执行结果：{resultSummary(a.result)}</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          <div>
            <div className="panel">
              <h2>实时审计时间线</h2>
              {events.length === 0 ? <Empty text="等待事件…" /> : (
                <div className="timeline">
                  {[...events].reverse().map((e) => (
                    <div className="t-event" key={e.id}>
                      <span className="t-time">{formatTime(e.ts)}</span>
                      <span><strong>{EVENT_LABEL[e.event] || e.event}</strong></span>
                      {e.action_id && <span className="mono muted">动作#{e.action_id}</span>}
                      {e.actor && e.actor !== 'gateway' && <span className="muted">（{e.actor}）</span>}
                      {e.event === 'action.policy' && e.detail && (
                        <div className="muted">
                          {e.detail.tool} → {DECISION_LABEL[e.detail.decision] || e.detail.decision}：
                          {e.detail.reason}
                        </div>
                      )}
                      {e.event === 'agent.step' && e.detail?.thought && (
                        <div className="muted">{String(e.detail.thought).slice(0, 160)}</div>
                      )}
                    </div>
                  ))}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
