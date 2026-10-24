import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'
import { cn } from '../../lib/utils'

const badgeVariants = cva('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors', {
  variants: {
    variant: {
      default: 'border-primary/40 bg-primary/15 text-primary-foreground',
      neutral: 'border-border bg-white/5 text-muted-foreground',
      up: 'border-up/40 bg-up/15 text-up',
      down: 'border-down/40 bg-down/15 text-down',
      gold: 'border-gold/40 bg-gold/10 text-gold',
    },
  },
  defaultVariants: { variant: 'default' },
})

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}
export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
