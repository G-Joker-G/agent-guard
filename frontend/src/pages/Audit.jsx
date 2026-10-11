import { useEffect, useState, useCallback } from 'react'
import { api, apiErrorMessage } from '../api'
import { formatTime } from '../labels'
import { ErrorBox, Empty } from '../components'

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
    <div className="panel">
      <h2>审计日志</h2>
      <div className="toolbar">
        <label>按任务筛选：
          <select value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)} style={{ marginLeft: 6 }}>
            <option value="">全部任务</option>
            {tasks.map((t) => <option key={t.id} value={t.id}>#{t.id} {t.title}</option>)}
          </select>
        </label>
        <button className="btn small" onClick={load}>刷新</button>
        <span style={{ marginLeft: 'auto' }}>
          {verify ? (
            verify.ok
              ? <span className="hash-ok">✓ 哈希链校验通过（已校验 {verify.checked} 条）</span>
              : <span className="hash-bad">✗ 哈希链校验失败</span>
          ) : <span className="muted">校验中…</span>}
          <button className="btn small" style={{ marginLeft: 8 }} onClick={check}>重新校验</button>
        </span>
      </div>
      <ErrorBox error={error} onClose={() => setError('')} />
      {events.length === 0 ? <Empty text="暂无审计事件" /> : (
        <ul className="timeline">
          {events.map((e) => (
            <li key={e.id}>
              <div className="t-time">
                {formatTime(e.ts)}
                {e.task_id ? <> · 任务 #{e.task_id}</> : null}
                {e.action_id ? <> · 动作 #{e.action_id}</> : null}
                {e.actor ? <> · {e.actor}</> : null}
              </div>
              <div className="t-event">{e.event}</div>
              <div className="t-detail">{e.detail || ''}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
