import * as ProgressPrimitive from '@radix-ui/react-progress'
import * as React from 'react'
import { cn } from '../../lib/utils'

export const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, ...props }, ref) => (
  <ProgressPrimitive.Root ref={ref} className={cn('relative h-2.5 w-full overflow-hidden rounded-full bg-white/10', className)} value={value} {...props}>
    <ProgressPrimitive.Indicator
      className="h-full rounded-full bg-gradient-to-r from-primary via-accent to-cyan-300 transition-all duration-700"
      style={{ width: `${value ?? 0}%` }}
    />
  </ProgressPrimitive.Root>
))
Progress.displayName = 'Progress'
