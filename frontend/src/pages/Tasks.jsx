import { useEffect, useState, useCallback } from 'react'
import { Plus, ArrowLeft, RefreshCw } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { SCENARIO_LABEL, paramsSummary, formatTime } from '../labels'
import { TaskBadge, ActionBadge } from '../components/status'
import { VerdictPipeline } from '../components/pipeline'
import { PageHeader, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input, Select } from '../components/ui/input'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/table'
import { Alert, AlertDescription } from '../components/ui/alert'

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
      <PageHeader title="任务中心" desc="创建 Agent 任务，跟踪每个任务的工具调用与网关裁决状态。" />

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="mb-4">
        <CardHeader><CardTitle>创建任务</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="text" placeholder="任务标题，例如：跟进客户 A 的续约" value={title}
              onChange={(e) => setTitle(e.target.value)} className="min-w-55 flex-1"
            />
            <Select value={scenario} onChange={(e) => setScenario(e.target.value)} className="w-48">
              <option value="followup">客户跟进（followup）</option>
              <option value="export_attack">越权攻击（export_attack）</option>
              <option value="batch">批量操作（batch）</option>
            </Select>
            <Button onClick={create} disabled={busy}><Plus size={15} /> 创建</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>任务列表（{tasks.length}）</CardTitle></CardHeader>
        <CardContent>
          {tasks.length === 0 ? (
            <EmptyState title="暂无任务" desc="创建一个任务，演示 Agent 会产出结构化工具请求。" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead><TableHead>标题</TableHead><TableHead>场景</TableHead>
                  <TableHead>状态</TableHead><TableHead>创建时间</TableHead><TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="tnum font-mono">#{t.id}</TableCell>
                    <TableCell className="max-w-72 truncate font-medium">{t.title}</TableCell>
                    <TableCell className="whitespace-nowrap">{SCENARIO_LABEL[t.scenario] || t.scenario}</TableCell>
                    <TableCell><TaskBadge status={t.status} /></TableCell>
                    <TableCell className="tnum whitespace-nowrap text-muted-foreground">{formatTime(t.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => onOpenTask(t.id)}>详情</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
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
      <PageHeader
        title={`任务 #${taskId}`}
        desc="每 1.5 秒自动刷新，跟踪状态流转。"
        actions={<Button variant="outline" size="sm" onClick={onBack}><ArrowLeft size={15} /> 返回任务列表</Button>}
      />

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!task ? (
        <EmptyState title="加载中…" />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              {task.title} <TaskBadge status={task.status} />
            </CardTitle>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
              <span>场景：{SCENARIO_LABEL[task.scenario] || task.scenario} <span className="font-mono text-xs">({task.scenario})</span></span>
              <span className="tnum">创建于 {formatTime(task.created_at)}</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="mb-4 flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => run(() => api.planTask(task.id), '生成计划')}>
                生成计划（plan）
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => run(() => api.advanceTask(task.id), '推进')}>
                推进（advance）
              </Button>
              <Button variant="ghost" size="sm" disabled={busy} onClick={load}>
                <RefreshCw size={14} /> 刷新
              </Button>
            </div>

            <div className="mb-2 text-sm font-medium">动作列表（{actions.length}）</div>
            {actions.length === 0 ? (
              <EmptyState title="暂无动作" desc="点击「生成计划」让演示 Agent 产出结构化请求。" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>序号</TableHead><TableHead>工具</TableHead><TableHead>裁决流水线</TableHead>
                    <TableHead>参数摘要</TableHead><TableHead>状态</TableHead><TableHead>判定理由</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {actions.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="tnum font-mono">#{a.seq}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs">{a.tool}</TableCell>
                      <TableCell className="min-w-52"><VerdictPipeline action={a} /></TableCell>
                      <TableCell className="max-w-64 text-muted-foreground">{paramsSummary(a.params)}</TableCell>
                      <TableCell className="whitespace-nowrap"><ActionBadge status={a.status} /></TableCell>
                      <TableCell className="max-w-48 text-xs text-muted-foreground">{a.decision_reason || a.decision || '—'}</TableCell>
                      <TableCell className="whitespace-nowrap text-right">
                        {executable(a.status) && (
                          <Button size="sm" disabled={busy}
                            onClick={() => run(() => api.executeAction(a.id), '执行')}>执行</Button>
                        )}
                        {a.status === 'needs_approval' && (
                          <Button variant="outline" size="sm" disabled={busy}
                            onClick={() => createApprovalFor(a.id)}>创建审批单</Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
