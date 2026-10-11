import { taskStatusOf, actionStatusOf } from './labels'

export function TaskBadge({ status }) {
  const s = taskStatusOf(status)
  return <span className={`badge ${s.cls}`}>{s.label}</span>
}

export function ActionBadge({ status }) {
  const s = actionStatusOf(status)
  return <span className={`badge ${s.cls}`}>{s.label}</span>
}

export function ErrorBox({ error, onClose }) {
  if (!error) return null
  return (
    <div className="alert err">
      <strong>请求失败：</strong>{error}
      {onClose && <button className="btn small" style={{ marginLeft: 12 }} onClick={onClose}>关闭</button>}
    </div>
  )
}

export function Empty({ text }) {
  return <div className="empty">{text || '暂无数据'}</div>
}
