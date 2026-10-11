import { useEffect, useState, useCallback } from 'react'
import { api, apiErrorMessage } from '../api'
import { formatTime } from '../labels'
import { ErrorBox, Empty } from '../components'

export function CustomersPage({ refreshKey }) {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try { setRows(await api.customers()); setError('') }
    catch (e) { setError(apiErrorMessage(e)) }
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  return (
    <div className="panel">
      <h2>客户数据 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>（只读 · 模拟 CRM 数据）</span></h2>
      <div className="toolbar"><button className="btn small" onClick={load}>刷新</button></div>
      <ErrorBox error={error} onClose={() => setError('')} />
      {rows.length === 0 ? <Empty text="暂无客户数据" /> : (
        <table className="tbl">
          <thead>
            <tr>
              {Object.keys(rows[0]).map((k) => <th key={k} className="mono">{k}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id ?? i}>
                {Object.keys(rows[0]).map((k) => (
                  <td key={k}>{typeof r[k] === 'object' ? JSON.stringify(r[k]) : String(r[k] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
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
    <div className="panel">
      <h2>发件箱 <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>（模拟发送记录，真实写入后端数据库）</span></h2>
      <div className="toolbar"><button className="btn small" onClick={load}>刷新</button></div>
      <ErrorBox error={error} onClose={() => setError('')} />
      {rows.length === 0 ? <Empty text="暂无发送记录" /> : (
        <table className="tbl">
          <thead>
            <tr><th>ID</th><th>收件人</th><th>主题</th><th>任务</th><th>发送时间</th></tr>
          </thead>
          <tbody>
            {rows.map((m, i) => (
              <tr key={m.id ?? i}>
                <td className="mono nowrap">#{m.id ?? i + 1}</td>
                <td>{m.to || m.recipient || '—'}</td>
                <td>{m.subject || '—'}</td>
                <td className="mono">{m.task_id ? `#${m.task_id}` : '—'}</td>
                <td className="nowrap muted">{formatTime(m.sent_at || m.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
