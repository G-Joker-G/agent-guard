import { cn } from '../lib/utils'

// 签名手法：网关裁决流水线 —— "提议 → 网关裁决 → 审批 → 执行"
// 颜色即状态。这是产品机制（模型只提议、网关才裁决）的可视化。
//
// 输入为 action 对象（含 status / decision），输出四段式状态条。
// 每段：done（实色）/ active（描边高亮）/ todo（灰）/ blocked（红色）。

function segState(stage, status, decision) {
  // stage: propose | verdict | approval | execute
  switch (stage) {
    case 'propose':
      return 'done' // 能进流水线即已被提议
    case 'verdict':
      if (!decision) return status === 'proposed' ? 'active' : 'todo'
      return 'done'
    case 'approval': {
      if (decision === 'allow') return 'skip'
      if (decision === 'deny') return 'skip'
      // needs_approval
      if (status === 'approved') return 'done'
      if (status === 'rejected') return 'blocked'
      return 'active'
    }
    case 'execute': {
      if (status === 'executed') return 'done'
      if (status === 'failed') return 'blocked'
      if (['denied', 'blocked_by_stop', 'rejected'].includes(status)) return 'blocked'
      if (status === 'approved' || status === 'allowed') return 'active'
      return 'todo'
    }
    default:
      return 'todo'
  }
}

const STAGES = [
  { key: 'propose', label: '提议' },
  { key: 'verdict', label: '网关裁决' },
  { key: 'approval', label: '审批' },
  { key: 'execute', label: '执行' },
]

const SEG_STYLE = {
  done: 'border-success/40 bg-success/15 text-success',
  active: 'border-warning/50 bg-warning/10 text-warning',
  todo: 'border-border bg-muted/40 text-muted-foreground',
  blocked: 'border-destructive/50 bg-destructive/15 text-destructive',
  skip: 'border-dashed border-border bg-transparent text-muted-foreground/60',
}

export function VerdictPipeline({ action }) {
  if (!action) return null
  const { status, decision } = action
  return (
    <div className="flex items-stretch gap-2" aria-label="网关裁决流水线">
      {STAGES.map((s) => {
        const st = segState(s.key, status, decision)
        const label = st === 'skip' ? `${s.label}·跳过` : s.label
        return (
          <div
            key={s.key}
            className={cn(
              'pipeline-seg flex-1 rounded-md border px-2 py-1.5 text-center text-xs font-medium',
              SEG_STYLE[st],
            )}
            title={label}
          >
            {label}
          </div>
        )
      })}
    </div>
  )
}
