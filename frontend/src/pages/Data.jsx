import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Users, Inbox } from 'lucide-react'
import { api, apiErrorMessage } from '../api'
import { formatTime } from '../labels'
import { PageHeader, EmptyState } from '../components/layout'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/table'
import { Alert, AlertDescription } from '../components/ui/alert'
import { cn } from '../lib/utils'

export function DataTabs({ sub, onChange }) {
  return (
    <div className="mb-4 flex gap-1 rounded-lg border border-border bg-muted/30 p-1 w-fit">
      {[
        { key: 'customers', label: '客户数据', icon: Users },
        { key: 'outbox', label: '发件箱', icon: Inbox },
      ].map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors',
            sub === t.key ? 'bg-card font-medium shadow-sm' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <t.icon size={14} /> {t.label}
        </button>
      ))}
    </div>
  )
}

export function CustomersPage({ refreshKey }) {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try { setRows(await api.customers()); setError('') }
    catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  return (
    <div>
      <PageHeader
        title="数据管理"
        desc="受控执行的读写对象：只读 CRM 客户数据与模拟发件箱的真实落库记录。"
        actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw size={14} /> 刷新</Button>}
      />
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>客户数据</CardTitle>
          <CardDescription>只读 · 模拟 CRM 数据（种子数据，演示越权拦截的攻击载荷藏在备注中）</CardDescription>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <EmptyState title="暂无客户数据" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {Object.keys(rows[0]).map((k) => <TableHead key={k} className="font-mono text-xs">{k}</TableHead>)}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={r.id ?? i}>
                    {Object.keys(rows[0]).map((k) => (
                      <TableCell key={k} className="max-w-64 truncate text-muted-foreground">
                        {typeof r[k] === 'object' ? JSON.stringify(r[k]) : String(r[k] ?? '—')}
                      </TableCell>
                    ))}
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

export function OutboxPage({ refreshKey }) {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try { setRows(await api.outbox()); setError('') }
    catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  return (
    <div>
      <PageHeader
        title="数据管理"
        desc="受控执行的读写对象：只读 CRM 客户数据与模拟发件箱的真实落库记录。"
        actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw size={14} /> 刷新</Button>}
      />
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>发件箱</CardTitle>
          <CardDescription>模拟发送记录，真实写入后端数据库</CardDescription>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <EmptyState title="暂无发送记录" desc="批准并执行 mail.send 后，记录会出现在这里。" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead><TableHead>收件人</TableHead><TableHead>主题</TableHead>
                  <TableHead>任务</TableHead><TableHead>发送时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((m, i) => (
                  <TableRow key={m.id ?? i}>
                    <TableCell className="tnum whitespace-nowrap font-mono">#{m.id ?? i + 1}</TableCell>
                    <TableCell>{m.to_email || '—'}</TableCell>
                    <TableCell className="max-w-72 truncate">{m.subject || '—'}</TableCell>
                    <TableCell className="font-mono">{m.task_id ? `#${m.task_id}` : '—'}</TableCell>
                    <TableCell className="tnum whitespace-nowrap text-muted-foreground">
                      {formatTime(m.sent_at || m.created_at)}
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
