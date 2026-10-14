import { useEffect, useState, useCallback } from 'react'
import { api, apiErrorMessage } from './api'
import { AppShell } from './components/layout'
import { CommandPalette } from './components/palette'
import { Alert, AlertDescription } from './components/ui/alert'
import { OctagonX } from 'lucide-react'
import { ErrorBoundary } from './ErrorBoundary'
import { DashboardPage } from './pages/Dashboard'
import { TasksPage, TaskDetailPage } from './pages/Tasks'
import { ApprovalsPage } from './pages/Approvals'
import { AuditPage } from './pages/Audit'
import { CustomersPage, OutboxPage, DataTabs } from './pages/Data'
import { DemoPage } from './pages/Demo'
import { LivePage } from './pages/Live'

export default function App() {
  const [tab, setTab] = useState('dashboard')
  const [dataSub, setDataSub] = useState('customers')
  const [openTaskId, setOpenTaskId] = useState(null)
  const [stopped, setStopped] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sseOk, setSseOk] = useState(false)
  // 管理口令（可选）：后端 .env 设了 GUARD_ADMIN_TOKEN 时在此填入，自动随管理/审批请求发送
  const [adminToken, setAdminToken] = useState(() => {
    try { return localStorage.getItem('guard_admin_token') || '' } catch { return '' }
  })
  // 主题：默认浅色清爽风，深色保留切换入口
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('guard_theme') || 'light' } catch { return 'light' }
  })
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try { localStorage.setItem('guard_theme', theme) } catch { /* 忽略存储异常 */ }
  }, [theme])

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

  function bump() { setRefreshKey((k) => k + 1) }

  function saveToken(v) {
    setAdminToken(v)
    try {
      if (v) localStorage.setItem('guard_admin_token', v)
      else localStorage.removeItem('guard_admin_token')
    } catch { /* 忽略存储异常 */ }
  }

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

  function nav(key) {
    if (key === 'customers' || key === 'outbox') {
      setDataSub(key)
      setTab('data')
    } else {
      setTab(key)
    }
    if (key !== 'tasks') setOpenTaskId(null)
  }

  const shellTab = tab === 'data' ? 'data' : tab

  return (
    <AppShell
      tab={shellTab}
      onNav={nav}
      pendingCount={pendingCount}
      stopped={stopped}
      busy={busy}
      onStop={doStop}
      onResume={doResume}
      adminToken={adminToken}
      onAdminToken={saveToken}
      connectionOk={sseOk}
      showConnection={tab === 'live'}
      onOpenPalette={() => setPaletteOpen(true)}
      theme={theme}
      onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
    >
      {stopped && (
        <Alert variant="destructive" className="mb-6">
          <OctagonX size={16} />
          <AlertDescription>
            紧急停止已生效：网关拒绝新动作，执行器拒绝一切执行。请人工确认后点击右上角「解除急停」。
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>
            {error}
            <button className="ml-3 underline underline-offset-2" onClick={() => setError('')}>关闭</button>
          </AlertDescription>
        </Alert>
      )}

      {tab === 'dashboard' && (
        <ErrorBoundary key="dashboard" name="总览">
          <DashboardPage onNav={nav} onOpenTask={(id) => { setTab('tasks'); setOpenTaskId(id) }} refreshKey={refreshKey} />
        </ErrorBoundary>
      )}
      {tab === 'live' && (
        <ErrorBoundary key="live" name="实时运行">
          <LivePage onSse={setSseOk} />
        </ErrorBoundary>
      )}
      {tab === 'tasks' && !openTaskId && (
        <ErrorBoundary key="tasks" name="任务中心">
          <TasksPage onOpenTask={setOpenTaskId} refreshKey={refreshKey} />
        </ErrorBoundary>
      )}
      {tab === 'tasks' && openTaskId && (
        <ErrorBoundary key={`tasks-${openTaskId}`} name="任务详情">
          <TaskDetailPage taskId={openTaskId} onBack={() => setOpenTaskId(null)} refreshKey={refreshKey} />
        </ErrorBoundary>
      )}
      {tab === 'approvals' && (
        <ErrorBoundary key="approvals" name="审批中心">
          <ApprovalsPage refreshKey={refreshKey} />
        </ErrorBoundary>
      )}
      {tab === 'audit' && (
        <ErrorBoundary key="audit" name="审计日志">
          <AuditPage refreshKey={refreshKey} />
        </ErrorBoundary>
      )}
      {tab === 'data' && (
        <ErrorBoundary key={`data-${dataSub}`} name="数据管理">
          <DataTabs sub={dataSub} onChange={setDataSub} />
          {dataSub === 'customers' ? <CustomersPage refreshKey={refreshKey} /> : <OutboxPage refreshKey={refreshKey} />}
        </ErrorBoundary>
      )}
      {tab === 'demo' && (
        <ErrorBoundary key="demo" name="演示">
          <DemoPage onReset={doReset} busy={busy} />
        </ErrorBoundary>
      )}

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onNav={nav}
        stopped={stopped}
        busy={busy}
        onStop={doStop}
        onResume={doResume}
      />
    </AppShell>
  )
}
