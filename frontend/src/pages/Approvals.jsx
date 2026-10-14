import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Check, X } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { paramsSummary, formatTime } from '../labels'
import { RiskBadge } from '../components/status'
import { PageHeader, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/table'
import { Alert, AlertDescription } from '../components/ui/alert'

export function ApprovalsPage({ refreshKey }) {
  const [list, setList] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [approver, setApprover] = useState('admin')
  const [note, setNote] = useState('')

  const load = useCallback(async () => {
    try { setList(await api.pendingApprovals()); setError('') }
    catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  async function decide(id, decision) {
    setBusy(true)
    try {
      await api.decideApproval(id, decision, approver || 'admin', note)
      setNote('')
      setError('')
      await load()
    } catch (e) { setError(apiErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader
        title="审批中心"
        desc="敏感工具调用在此等待人工决策。批准后生成一次一用的 scope 绑定，执行时网关复查。"
        actions={
          <Button variant="outline" size="sm" onClick={load}><RefreshCw size={14} /> 刷新</Button>
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
            <span className="text-sm text-muted-foreground">批准人</span>
            <Input type="text" value={approver} onChange={(e) => setApprover(e.target.value)} className="h-9 w-32" />
            <Input
              type="text" placeholder="审批备注（可选）" value={note}
              onChange={(e) => setNote(e.target.value)} className="min-w-52 flex-1"
            />
          </div>
        </CardHeader>
        <CardContent>
          {list.length === 0 ? (
            <EmptyState title="暂无待审批事项" desc="新的敏感工具调用出现时，会在这里等待人工决策。" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>审批单</TableHead><TableHead>工具</TableHead><TableHead>目标</TableHead>
                  <TableHead>参数摘要</TableHead><TableHead>风险</TableHead><TableHead>申请时间</TableHead>
                  <TableHead className="text-right">决策</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((a) => {
                  const act = a.action || {}
                  return (
                    <TableRow key={a.id}>
                      <TableCell className="tnum whitespace-nowrap font-mono">#{a.id}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs">{act.tool || a.tool || '—'}</TableCell>
                      <TableCell className="whitespace-nowrap">{targetOf(act)}</TableCell>
                      <TableCell className="max-w-72 text-muted-foreground">{paramsSummary(act.params || a.params)}</TableCell>
                      <TableCell><RiskBadge risk={a.risk || act.risk} /></TableCell>
                      <TableCell className="tnum whitespace-nowrap text-muted-foreground">{formatTime(a.created_at)}</TableCell>
                      <TableCell className="whitespace-nowrap text-right">
                        <div className="inline-flex gap-2">
                          <Button size="sm" variant="success" disabled={busy} onClick={() => decide(a.id, 'approve')}>
                            <Check size={14} /> 批准
                          </Button>
                          <Button size="sm" variant="destructive" disabled={busy} onClick={() => decide(a.id, 'reject')}>
                            <X size={14} /> 拒绝
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function targetOf(act) {
  const p = act.params || {}
  if (p.customer_id !== undefined) return `客户 #${p.customer_id}`
  if (p.to) return p.to
  return '—'
}
