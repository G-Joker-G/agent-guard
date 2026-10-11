// 状态 / 场景 / 工具 的中文映射与样式（与 PLAN.md 契约枚举对齐，未知值原样兜底）

export const SCENARIO_LABEL = {
  followup: '客户跟进',
  export_attack: '越权攻击',
  batch: '批量操作',
}

export const TASK_STATUS = {
  created: { label: '已创建', cls: 'st-created' },
  running: { label: '运行中', cls: 'st-running' },
  pending_approval: { label: '等待审批', cls: 'st-waiting' },
  completed: { label: '已完成', cls: 'st-done' },
  done: { label: '已完成', cls: 'st-done' },
  rejected: { label: '已拒绝', cls: 'st-rejected' },
  stopped: { label: '已急停', cls: 'st-stopped' },
}

export const ACTION_STATUS = {
  proposed: { label: '已提议', cls: 'st-created' },
  allowed: { label: '允许自动执行', cls: 'st-running' },
  needs_approval: { label: '等待审批', cls: 'st-waiting' },
  denied: { label: '策略拒绝', cls: 'st-denied' },
  approved: { label: '已批准', cls: 'st-approved' },
  rejected: { label: '已驳回', cls: 'st-rejected' },
  blocked_by_stop: { label: '急停拦截', cls: 'st-stopped' },
  executed: { label: '已执行', cls: 'st-done' },
  failed: { label: '执行失败', cls: 'st-failed' },
}

export const DECISION_LABEL = { allow: '放行', needs_approval: '需审批', deny: '拒绝' }

export function taskStatusOf(s) {
  return TASK_STATUS[s] || { label: s || '未知', cls: 'st-unknown' }
}
export function actionStatusOf(s) {
  return ACTION_STATUS[s] || { label: s || '未知', cls: 'st-unknown' }
}

// 动作参数摘要：挑关键字段，人类可读
export function paramsSummary(params) {
  if (!params || typeof params !== 'object') return '—'
  const bits = []
  if (params.customer_id !== undefined) bits.push(`客户#${params.customer_id}`)
  if (params.to) bits.push(`收件人 ${params.to}`)
  if (params.subject) bits.push(`主题「${params.subject}」`)
  if (params.body) bits.push(`正文 ${String(params.body).length} 字`)
  if (params.field || params.updates) bits.push(`更新 ${params.field || JSON.stringify(params.updates)}`)
  if (params.batch) bits.push('批量发送')
  const rest = Object.keys(params).filter(
    (k) => !['customer_id', 'to', 'subject', 'body', 'field', 'updates', 'batch'].includes(k),
  )
  rest.forEach((k) => bits.push(`${k}=${JSON.stringify(params[k])}`))
  return bits.length ? bits.join('；') : '—'
}

export function formatTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  if (isNaN(d)) return String(ts)
  return d.toLocaleString('zh-CN', { hour12: false })
}
