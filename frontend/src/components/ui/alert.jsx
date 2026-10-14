import { cva } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const alertVariants = cva(
  'relative w-full rounded-lg border px-4 py-3 text-sm grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 [&>svg]:size-4 [&>svg]:translate-y-0.5',
  {
    variants: {
      variant: {
        default: 'bg-card text-foreground border-border',
        destructive: 'border-destructive/40 bg-destructive/10 text-destructive [&>svg]:text-destructive',
        warning: 'border-warning/40 bg-warning/10 text-warning [&>svg]:text-warning',
        success: 'border-success/40 bg-success/10 text-success [&>svg]:text-success',
        info: 'border-info/40 bg-info/10 text-info [&>svg]:text-info',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

function Alert({ className, variant, ...props }) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}

function AlertTitle({ className, ...props }) {
  return <h5 className={cn('col-start-2 font-medium leading-none tracking-tight', className)} {...props} />
}

function AlertDescription({ className, ...props }) {
  return <div className={cn('col-start-2 text-sm [&_p]:leading-relaxed', className)} {...props} />
}

export { Alert, AlertTitle, AlertDescription }
