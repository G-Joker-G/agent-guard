import { useEffect, useState, useCallback } from 'react'
import { api, apiErrorMessage } from '../api'
import { SCENARIO_LABEL, paramsSummary, formatTime } from '../labels'
import { TaskBadge, ActionBadge, ErrorBox, Empty } from '../components'

export function TasksPage({ onOpenTask, refreshKey }) {
  const [tasks, setTasks] = useState([])
  const [title, setTitle] = useState('')
  const [scenario, setScenario] = useState('followup')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try { setTasks(await api.listTasks()) }
    catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  async function create() {
    if (!title.trim()) { setError('请填写任务标题'); return }
    setBusy(true)
    try {
      const t = await api.createTask(title.trim(), scenario)
      setTitle('')
      setError('')
      onOpenTask(t.id)
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <div>
      <div className="panel">
        <h2>创建任务</h2>
        <div className="row">
          <input
            type="text" placeholder="任务标题，例如：跟进客户 A 的续约" value={title}
            onChange={(e) => setTitle(e.target.value)} style={{ flex: 1, minWidth: 220 }}
          />
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            <option value="followup">客户跟进（followup）</option>
            <option value="export_attack">越权攻击（export_attack）</option>
            <option value="batch">批量操作（batch）</option>
          </select>
          <button className="btn primary" onClick={create} disabled={busy}>创建</button>
        </div>
        <ErrorBox error={error} onClose={() => setError('')} />
      </div>

      <div className="panel">
        <h2>任务列表</h2>
        {tasks.length === 0 ? <Empty text="暂无任务，请先创建一个" /> : (
          <table className="tbl">
            <thead>
              <tr><th>ID</th><th>标题</th><th>场景</th><th>状态</th><th>创建时间</th><th></th></tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td className="mono">#{t.id}</td>
                  <td>{t.title}</td>
                  <td className="nowrap">{SCENARIO_LABEL[t.scenario] || t.scenario}</td>
                  <td><TaskBadge status={t.status} /></td>
                  <td className="nowrap muted">{formatTime(t.created_at)}</td>
                  <td><button className="btn small" onClick={() => onOpenTask(t.id)}>详情</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export function TaskDetailPage({ taskId, onBack, refreshKey }) {
  const [task, setTask] = useState(null)
  const [actions, setActions] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const d = await api.getTask(taskId)
      setTask(d.task || d)
      setActions(d.actions || [])
      setError('')
    } catch (e) { setError(apiErrorMessage(e)) }
  }, [taskId])

  // 轮询：每 1.5s 拉一次任务详情，展示状态流转
  useEffect(() => {
    load()
    const timer = setInterval(load, 1500)
    return () => clearInterval(timer)
  }, [load, refreshKey])

  async function run(fn, label) {
    setBusy(true)
    try { await fn(); await load(); setError('') }
    catch (e) { setError(`${label}失败：${apiErrorMessage(e)}`) }
    finally { setBusy(false) }
  }

  async function createApprovalFor(actionId) {
    await run(async () => {
      const a = await api.createApproval(actionId)
      setError('')
      alert(`审批单已创建：#${a.id}`)
    }, '创建审批单')
  }

  const executable = (s) => ['allowed', 'approved'].includes(s)

  return (
    <div>
      <div className="toolbar">
        <button className="btn small" onClick={onBack}>← 返回任务列表</button>
        <span className="poll-note">每 1.5 秒自动刷新，跟踪状态流转</span>
      </div>
      <ErrorBox error={error} onClose={() => setError('')} />
      {!task ? <Empty text="加载中…" /> : (
        <div className="panel">
          <h2>任务 #{task.id} · {task.title}</h2>
          <dl className="kv">
            <dt>场景</dt><dd>{SCENARIO_LABEL[task.scenario] || task.scenario}（{task.scenario}）</dd>
            <dt>状态</dt><dd><TaskBadge status={task.status} /></dd>
            <dt>创建时间</dt><dd className="muted">{formatTime(task.created_at)}</dd>
          </dl>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={busy} onClick={() => run(() => api.planTask(task.id), '生成计划')}>
              生成计划（plan）
            </button>
            <button className="btn" disabled={busy} onClick={() => run(() => api.advanceTask(task.id), '推进')}>
              推进（advance）
            </button>
          </div>

          <h3>动作列表（{actions.length}）</h3>
          {actions.length === 0 ? <Empty text="暂无动作，点击「生成计划」让演示 Agent 产出结构化请求" /> : (
            <table className="tbl">
              <thead>
                <tr><th>序号</th><th>工具</th><th>参数摘要</th><th>状态</th><th>判定理由</th><th>操作</th></tr>
              </thead>
              <tbody>
                {actions.map((a) => (
                  <tr key={a.id}>
                    <td className="mono nowrap">#{a.seq}</td>
                    <td className="mono nowrap">{a.tool}</td>
                    <td>{paramsSummary(a.params)}</td>
                    <td className="nowrap"><ActionBadge status={a.status} /></td>
                    <td className="muted">{a.decision_reason || a.decision || '—'}</td>
                    <td className="nowrap">
                      {executable(a.status) && (
                        <button className="btn small primary" disabled={busy}
                          onClick={() => run(() => api.executeAction(a.id), '执行')}>执行</button>
                      )}
                      {a.status === 'needs_approval' && (
                        <button className="btn small" disabled={busy} style={{ marginLeft: 6 }}
                          onClick={() => createApprovalFor(a.id)}>创建审批单</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
