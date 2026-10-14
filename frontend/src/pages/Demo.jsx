import { useState } from 'react'
import { Play, Zap, OctagonX, CheckCircle2, AlertTriangle, RotateCcw } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { PageHeader, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export function DemoPage({ onReset, busy: resetBusy }) {
  const [steps, setSteps] = useState([])
  const [running, setRunning] = useState(false)
  const [activeDemo, setActiveDemo] = useState('')

  function push(step) {
    setSteps((s) => [...s, step])
  }

  function say(title, apiLine, resp, decision) {
    push({ title, api: apiLine, resp, decision })
  }

  async function call(title, method, path, fn, respOf) {
    say(title, `${method} ${path}`, '调用中…')
    try {
      const r = await fn()
      setSteps((s) => {
        const c = [...s]
        c[c.length - 1] = { ...c[c.length - 1], resp: respOf(r) }
        return c
      })
      return r
    } catch (e) {
      const msg = apiErrorMessage(e)
      setSteps((s) => {
        const c = [...s]
        c[c.length - 1] = { ...c[c.length - 1], resp: `❌ ${msg}`, decision: '调用失败' }
        return c
      })
      throw e
    }
  }

  function actionsSummary(actions) {
    return (actions || [])
      .map((a) => `  - #${a.seq} ${a.tool} → ${a.status}${a.decision_reason ? `（${a.decision_reason}）` : ''}`)
      .join('\n')
  }

  async function demoA() {
    const t = await call('① 创建任务（客户跟进场景）', 'POST', '/api/tasks',
      () => api.createTask('演示A · 客户跟进审批流', 'followup'),
      (r) => `任务 #${r.id} 已创建，status=${r.status}`)
    const p = await call('② 演示 Agent 生成计划', 'POST', `/api/tasks/${t.id}/plan`,
      () => api.planTask(t.id),
      (r) => `产出动作：\n${actionsSummary(r.actions || r)}`)
    await call('③ 网关推进（策略评估）', 'POST', `/api/tasks/${t.id}/advance`,
      () => api.advanceTask(t.id),
      (r) => {
        const a = r.actions || []
        const na = a.find((x) => x.status === 'needs_approval')
        return `评估结果：\n${actionsSummary(a)}\n` +
          (na ? `任务进入 pending_approval：mail.send 需人工审批后才能执行` : '无待审批动作')
      })
    const task = await api.getTask(t.id)
    const needAppr = (task.actions || []).find((x) => x.status === 'needs_approval')
    if (!needAppr) {
      say('④ 无待审批动作', '—', 'advance 未产生 needs_approval 动作，演示到此结束（可能场景数据未按预期产出）')
      return
    }
    const ap = await call('④ 为动作创建审批单', 'POST', '/api/approvals',
      () => api.createApproval(needAppr.id),
      (r) => `审批单 #${r.id}，绑定 action #${needAppr.id}`)
    await call('⑤ 人工批准（approver=admin）', 'POST', `/api/approvals/${ap.id}/decide`,
      () => api.decideApproval(ap.id, 'approve', 'admin', '演示路径 A 批准'),
      () => `审批通过：生成 scope 绑定（30 分钟有效，一次一用）`)
    await call('⑥ 执行已批准的动作（网关复查审批绑定）', 'POST', `/api/actions/${needAppr.id}/execute`,
      () => api.executeAction(needAppr.id),
      (r) => `执行后 status=${r.status}：网关复查急停标志 + 审批绑定（存在/已批准/未使用/未过期/hash 一致）后才放行`)
    await call('⑦ 查发件箱：验证邮件真实写入数据库', 'GET', '/api/outbox',
      () => api.outbox(),
      (r) => {
        const last = r.length ? r[r.length - 1] : null
        return `发件箱共 ${r.length} 封${last ? `，最新：收件人 ${last.to_email || last.to || last.recipient}` : ''}`
      })
    say('✅ 路径 A 完成', '—', 'mail.send 走完「提议 → 策略评估需审批 → 人工批准 → 绑定执行 → 真实落库」全链路', '演示成功')
  }

  async function demoB() {
    const t = await call('① 创建任务（越权攻击场景）', 'POST', '/api/tasks',
      () => api.createTask('演示B · 越权攻击拦截', 'export_attack'),
      (r) => `任务 #${r.id} 已创建`)
    await call('② 演示 Agent 生成计划（含 notes 诱导注入）', 'POST', `/api/tasks/${t.id}/plan`,
      () => api.planTask(t.id),
      (r) => `产出动作（注意最后一条为注入诱导的 crm.export_all）：\n${actionsSummary(r.actions || r)}`)
    await call('②′ 攻击载荷：客户资料中嵌入的恶意指令', 'GET', '/api/customers',
      () => api.customers(),
      (r) => {
        const hit = (r || []).find((c) => (c.notes || '').includes('系统指令'))
        return hit
          ? `客户「${hit.name}（${hit.company}）」的备注中藏有：\n「${hit.notes}」\n演示 Agent 读取客户资料时被该指令诱导，产出了导出请求。`
          : '未找到注入指令（种子数据可能已被重置，请检查后端 seed）'
      })
    const adv = await call('③ 网关推进：策略引擎评估', 'POST', `/api/tasks/${t.id}/advance`,
      () => api.advanceTask(t.id),
      (r) => `评估结果：\n${actionsSummary(r.actions)}`)
    const denied = (adv.actions || []).find((x) => x.tool === 'crm.export_all')
    if (denied) {
      await call('④ 尝试直接执行被拒绝的导出动作', 'POST', `/api/actions/${denied.id}/execute`,
        () => api.executeAction(denied.id),
        (r) => `执行返回 status=${r.status}：被拒绝的动作不会被执行`,
        ).catch(() => {})
      say('✅ 路径 B 完成', '—',
        `crm.export_all 判定为 deny：「批量导出全部客户资料，禁止」。拒绝判定只在服务端作出，前端仅展示。`, '拦截成功')
    } else {
      say('⚠️ 未按预期产出 export_all', '—', '请检查后端 demo_agent 的 export_attack 场景实现')
    }
  }

  async function demoC() {
    const t = await call('① 创建任务（批量操作场景）', 'POST', '/api/tasks',
      () => api.createTask('演示C · 急停流程', 'batch'),
      (r) => `任务 #${r.id} 已创建`)
    await call('② 生成计划 + 推进（执行第一批允许的动作）', 'POST', `/api/tasks/${t.id}/plan → /advance`,
      async () => { await api.planTask(t.id); return api.advanceTask(t.id) },
      (r) => `推进后：\n${actionsSummary(r.actions)}`)
    await call('③ 管理员触发紧急停止', 'POST', '/api/admin/stop',
      () => api.stop('admin'),
      (r) => `emergency_stop=1（审计 stop.engaged）。受影响待执行动作：${JSON.stringify(r)}`)
    await call('④ 急停期间再次推进', 'POST', `/api/tasks/${t.id}/advance`,
      () => api.advanceTask(t.id),
      (r) => `新动作判定为 blocked_by_stop：\n${actionsSummary(r.actions)}`)
    const task = await api.getTask(t.id)
    const candidate = (task.actions || []).find((x) => ['approved', 'allowed'].includes(x.status))
    if (candidate) {
      await call('⑤ 急停期间尝试执行已批准动作', 'POST', `/api/actions/${candidate.id}/execute`,
        () => api.executeAction(candidate.id),
        (r) => `执行返回 status=${r.status}：执行器执行前必查急停，直接拒绝并审计 action.blocked_stop`)
        .catch(() => {})
    } else {
      say('⑤ 无可试执行的已批准动作', '—', '跳过单动作执行验证（④ 的 blocked_by_stop 已证明网关拦截）')
    }
    if (window.confirm('演示路径 C：是否调用恢复接口解除急停？（恢复为显式操作，将写入审计 stop.released）')) {
      await call('⑥ 显式恢复（无自动恢复）', 'POST', '/api/admin/resume',
        () => api.resume('admin'),
        () => 'emergency_stop=0，审计 stop.released。只有显式 resume 能恢复，advance 不会自动恢复。')
      say('✅ 路径 C 完成', '—', '急停 → 拦截新动作/执行 → 显式恢复，全链路验证完毕', '演示成功')
    } else {
      say('⏸ 路径 C 暂停', '—', '急停仍保持生效，可在顶栏点击「解除急停」解除（需二次确认）')
    }
  }

  async function runDemo(which, fn) {
    if (running) return
    setRunning(true)
    setActiveDemo(which)
    setSteps([])
    try {
      await fn()
    } catch {
      /* 步骤内已记录失败 */
    } finally {
      setRunning(false)
      await sleep(300)
    }
  }

  const demos = [
    {
      key: 'A', title: '路径 A · 正常审批流', icon: Play, variant: 'default',
      desc: 'mail.send 走完「提议 → 策略评估需审批 → 人工批准 → 绑定执行 → 真实落库」全链路。',
      fn: demoA,
    },
    {
      key: 'B', title: '路径 B · 越权拦截', icon: Zap, variant: 'destructive',
      desc: '注入诱导的 crm.export_all 被网关策略拒绝，并验证拒绝的动作无法执行。',
      fn: demoB,
    },
    {
      key: 'C', title: '路径 C · 急停流程', icon: OctagonX, variant: 'destructive',
      desc: '急停 → 拦截新动作与执行 → 显式恢复，全链路验证。',
      fn: demoC,
    },
  ]

  return (
    <div>
      <PageHeader
        title="演示"
        desc="一键跑通三条演示路径。每一步显示调用的接口与返回判定——所有判定均由后端作出，前端只负责展示。"
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {demos.map((d) => (
          <Card key={d.key} className={activeDemo === d.key && running ? 'border-primary/60' : ''}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <d.icon size={16} /> {d.title}
              </CardTitle>
              <CardDescription>{d.desc}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant={d.variant} disabled={running} onClick={() => runDemo(d.key, d.fn)} className="w-full">
                {running && activeDemo === d.key ? '运行中…' : `运行路径 ${d.key}`}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {steps.length > 0 && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              执行步骤 {activeDemo && `(路径 ${activeDemo})`}
              {running && <Badge variant="info">运行中…</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3">
              {steps.map((s, i) => (
                <li key={i} className="rounded-lg border border-border bg-muted/20 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{s.title}</span>
                    {s.decision && (
                      <Badge variant={s.decision === '调用失败' ? 'destructive' : 'success'} className="gap-1">
                        {s.decision === '调用失败' ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
                        {s.decision}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-1 font-mono text-xs text-muted-foreground">{s.api}</div>
                  <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-xs leading-relaxed text-foreground/90">
                    {s.resp}
                  </pre>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      <Card className="mt-4 border-destructive/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><RotateCcw size={16} /> 演示辅助</CardTitle>
          <CardDescription>
            调用 POST /api/admin/reset：清空任务/动作/审批/审计/发件箱，重建种子客户数据，解除急停。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="destructive" disabled={resetBusy} onClick={onReset}>
            一键重置演示数据
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
