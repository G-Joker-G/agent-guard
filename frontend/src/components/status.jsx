import { Badge } from './ui/badge'
import { taskStatusOf, actionStatusOf, DECISION_LABEL } from '../labels'

// 状态 → 语义 badge 的唯一映射。所有页面共用，保证"同一状态同一颜色"。

const TASK_VARIANT = {
  created: 'muted', planned: 'muted',
  in_progress: 'info', running: 'info',
  pending_approval: 'warning',
  completed: 'success', done: 'success',
  failed: 'destructive', rejected: 'destructive',
  stopped: 'destructive',
}

const ACTION_VARIANT = {
  proposed: 'muted',
  allowed: 'info',
  needs_approval: 'warning',
  denied: 'destructive',
  approved: 'success',
  rejected: 'destructive',
  blocked_by_stop: 'destructive',
  executed: 'success',
  failed: 'destructive',
}

const DECISION_VARIANT = { allow: 'success', needs_approval: 'warning', deny: 'destructive' }

const RISK_VARIANT = { low: 'success', medium: 'warning', high: 'destructive' }

export function TaskBadge({ status }) {
  const s = taskStatusOf(status)
  return <Badge variant={TASK_VARIANT[status] || 'muted'}>{s.label}</Badge>
}

export function ActionBadge({ status }) {
  const s = actionStatusOf(status)
  return <Badge variant={ACTION_VARIANT[status] || 'muted'}>{s.label}</Badge>
}

export function DecisionBadge({ decision }) {
  if (!decision) return null
  return <Badge variant={DECISION_VARIANT[decision] || 'muted'}>{DECISION_LABEL[decision] || decision}</Badge>
}

export function RiskBadge({ risk }) {
  if (!risk) return null
  const label = { low: '低风险', medium: '中风险', high: '高风险' }[risk] || risk
  return <Badge variant={RISK_VARIANT[risk] || 'muted'}>{label}</Badge>
}

const ORIGIN_LABEL = { web: '控制台', demo: '演示 Agent', mcp: 'MCP 客户端', llm: 'LLM Agent' }

export function OriginBadge({ origin }) {
  if (!origin) return null
  return <Badge variant="secondary">{ORIGIN_LABEL[origin] || origin}</Badge>
}

const EVENT_META = {
  'task.created': { label: '任务创建', variant: 'info' },
  'action.proposed': { label: 'Agent 提议动作', variant: 'muted' },
  'action.policy': { label: '网关策略评估', variant: 'info' },
  'approval.created': { label: '审批单创建', variant: 'warning' },
  'approval.approved': { label: '审批通过', variant: 'success' },
  'approval.rejected': { label: '审批驳回', variant: 'destructive' },
  'approval.timeout': { label: '审批等待超时', variant: 'warning' },
  'action.executed': { label: '执行成功', variant: 'success' },
  'action.denied': { label: '策略拒绝', variant: 'destructive' },
  'action.failed': { label: '执行失败', variant: 'destructive' },
  'action.blocked_stop': { label: '急停拦截', variant: 'destructive' },
  'action.execute_rejected': { label: '执行被拒', variant: 'destructive' },
  'stop.engaged': { label: '紧急停止', variant: 'destructive' },
  'stop.released': { label: '解除急停', variant: 'success' },
  'data.reset': { label: '数据重置', variant: 'muted' },
  'agent.step': { label: 'Agent 推理', variant: 'muted' },
  'agent.error': { label: 'Agent 出错', variant: 'destructive' },
}

export function EventBadge({ event }) {
  const m = EVENT_META[event]
  if (!m) return <Badge variant="muted">{event}</Badge>
  return <Badge variant={m.variant}>{m.label}</Badge>
}

export function eventLabelOf(event) {
  return (EVENT_META[event] && EVENT_META[event].label) || event
}
