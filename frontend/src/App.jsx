import { useEffect, useState, useCallback } from 'react'
import { api, apiErrorMessage } from './api'
import { TasksPage, TaskDetailPage } from './pages/Tasks'
import { ApprovalsPage } from './pages/Approvals'
import { AuditPage } from './pages/Audit'
import { CustomersPage, OutboxPage } from './pages/Data'
import { DemoPage } from './pages/Demo'
import { LivePage } from './pages/Live'
import { ErrorBox } from './components'

const TABS = [
  { key: 'live', label: '实时运行' },
  { key: 'tasks', label: '任务中心' },
  { key: 'approvals', label: '审批中心' },
  { key: 'audit', label: '审计日志' },
  { key: 'customers', label: '客户数据' },
  { key: 'outbox', label: '发件箱' },
  { key: 'demo', label: '演示' },
]

export default function App() {
  const [tab, setTab] = useState('live')
  const [openTaskId, setOpenTaskId] = useState(null)
  const [stopped, setStopped] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [busy, setBusy] = useState(false)

  const refreshStatus = useCallback(async () => {
    try {
      const s = await api.status()
      setStopped(!!s.emergency_stop)
      const p = await api.pendingApprovals()
      setPendingCount(Array.isArray(p) ? p.length : 0)
    } catch {
      /* 后端未启动时静默 */
    }
  }, [])

  useEffect(() => {
    refreshStatus()
    const timer = setInterval(refreshStatus, 2000)
    return () => clearInterval(timer)
  }, [refreshStatus])

  useEffect(() => {
    document.body.classList.toggle('has-stop', stopped)
  }, [stopped])

  function bump() { setRefreshKey((k) => k + 1) }

  async function doStop() {
    setBusy(true)
    try {
      await api.stop('admin')
      setError('')
      bump()
      await refreshStatus()
    } catch (e) { setError(`紧急停止失败：${apiErrorMessage(e)}`) }
    finally { setBusy(false) }
  }

  async function doResume() {
    if (!window.confirm('确定要解除紧急停止、恢复系统运行吗？此操作将写入审计日志（stop.released）。')) return
    setBusy(true)
    try {
      await api.resume('admin')
      setError('')
      bump()
      await refreshStatus()
    } catch (e) { setError(`恢复失败：${apiErrorMessage(e)}`) }
    finally { setBusy(false) }
  }

  async function doReset() {
    if (!window.confirm('一键重置：清空任务/动作/审批/审计/发件箱并重建种子客户数据、解除急停。确定吗？')) return
    setBusy(true)
    try {
      await api.reset()
      setError('')
      bump()
      await refreshStatus()
    } catch (e) { setError(`重置失败：${apiErrorMessage(e)}`) }
    finally { setBusy(false) }
  }

  return (
    <div>
      <div className="sim-banner">Agent 模式：演示 Agent（确定性模拟）/ 真实 LLM（需在 .env 配置 LLM_API_KEY）—— 无论哪种 Agent，所有执行必经服务端网关</div>
      {stopped && (
        <div className="stop-banner">⚠️ 紧急停止已生效：网关拒绝新动作，执行器拒绝一切执行。请人工确认后点击「恢复」解除。</div>
      )}

      <header className="topbar">
        <div className="brand">Agent Guard<small>执行控制层 · Demo</small></div>
        <nav className="nav">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? 'active' : ''}
              onClick={() => { setTab(t.key); if (t.key !== 'tasks') setOpenTaskId(null) }}
            >
              {t.label}
              {t.key === 'approvals' && pendingCount > 0 && `（${pendingCount}）`}
            </button>
          ))}
        </nav>
        <div className="top-actions">
          <span className="stop-state">{stopped ? '状态：已急停' : '状态：运行中'}</span>
          {!stopped ? (
            <button className="btn danger" disabled={busy} onClick={doStop}>紧急停止</button>
          ) : (
            <button className="btn ok" disabled={busy} onClick={doResume}>恢复</button>
          )}
        </div>
      </header>

      <main className="main">
        <ErrorBox error={error} onClose={() => setError('')} />
        {tab === 'live' && <LivePage />}
        {tab === 'tasks' && !openTaskId && (
          <TasksPage onOpenTask={setOpenTaskId} refreshKey={refreshKey} />
        )}
        {tab === 'tasks' && openTaskId && (
          <TaskDetailPage taskId={openTaskId} onBack={() => setOpenTaskId(null)} refreshKey={refreshKey} />
        )}
        {tab === 'approvals' && <ApprovalsPage refreshKey={refreshKey} />}
        {tab === 'audit' && <AuditPage refreshKey={refreshKey} />}
        {tab === 'customers' && <CustomersPage refreshKey={refreshKey} />}
        {tab === 'outbox' && <OutboxPage refreshKey={refreshKey} />}
        {tab === 'demo' && (
          <div>
            <DemoPage />
            <div className="panel">
              <h2>演示辅助</h2>
              <div className="row">
                <button className="btn danger" disabled={busy} onClick={doReset}>一键重置演示数据</button>
                <span className="muted">调用 POST /api/admin/reset：清空任务/动作/审批/审计/发件箱，重建种子客户数据，解除急停。</span>
              </div>
            </div>
          </div>
        )}
        <div className="footer">
          Agent Guard V2 · 所有权限判定均由后端网关作出，前端仅做展示 · 审计即事件源
        </div>
      </main>
    </div>
  )
}
