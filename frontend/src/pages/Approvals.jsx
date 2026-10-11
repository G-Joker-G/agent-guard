import { useEffect, useState, useCallback } from 'react'
import { api, apiErrorMessage } from '../api'
import { paramsSummary, formatTime } from '../labels'
import { ErrorBox, Empty } from '../components'

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
    <div className="panel">
      <h2>审批中心 · 待审批</h2>
      <div className="toolbar">
        <label>批准人：<input type="text" value={approver} onChange={(e) => setApprover(e.target.value)} style={{ width: 120 }} /></label>
        <input type="text" placeholder="审批备注（可选）" value={note}
          onChange={(e) => setNote(e.target.value)} style={{ flex: 1, minWidth: 200 }} />
        <button className="btn small" onClick={load}>刷新</button>
      </div>
      <ErrorBox error={error} onClose={() => setError('')} />
      {list.length === 0 ? <Empty text="暂无待审批事项" /> : (
        <table className="tbl">
          <thead>
            <tr><th>审批单</th><th>操作</th><th>目标</th><th>参数摘要</th><th>风险说明</th><th>申请时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {list.map((a) => {
              const act = a.action || {}
              return (
                <tr key={a.id}>
                  <td className="mono nowrap">#{a.id}</td>
                  <td className="mono nowrap">{act.tool || a.tool || '—'}</td>
                  <td>{targetOf(act)}</td>
                  <td>{paramsSummary(act.params || a.params)}</td>
                  <td className="muted">{a.risk || act.decision_reason || '—'}</td>
                  <td className="nowrap muted">{formatTime(a.created_at)}</td>
                  <td className="nowrap">
                    <button className="btn small ok" disabled={busy} onClick={() => decide(a.id, 'approve')}>批准</button>
                    <button className="btn small danger" disabled={busy} style={{ marginLeft: 6 }}
                      onClick={() => decide(a.id, 'reject')}>拒绝</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

function targetOf(act) {
  const p = act.params || {}
  if (p.customer_id !== undefined) return `客户 #${p.customer_id}`
  if (p.to) return p.to
  return '—'
}
