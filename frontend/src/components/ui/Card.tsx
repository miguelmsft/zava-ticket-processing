import { cn } from '../../lib/utils'

type AccentColor = 'indigo' | 'teal' | 'violet' | 'emerald' | 'blue' | 'amber'

const ACCENT_BORDER: Record<AccentColor, string> = {
  indigo: 'border-l-[3px] border-l-indigo-500',
  teal: 'border-l-[3px] border-l-teal-500',
  violet: 'border-l-[3px] border-l-violet-500',
  emerald: 'border-l-[3px] border-l-emerald-500',
  blue: 'border-l-[3px] border-l-blue-500',
  amber: 'border-l-[3px] border-l-amber-500',
}

interface CardProps {
  title?: string
  subtitle?: string
  icon?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
  noPadding?: boolean
  accent?: AccentColor
}

export default function Card({
  title,
  subtitle,
  icon,
  action,
  children,
  className,
  noPadding,
  accent,
}: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-slate-200/80 bg-white/80 backdrop-blur-sm shadow-soft',
        accent && ACCENT_BORDER[accent],
        className,
      )}
    >
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-slate-100/80 px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            {icon && <span className="text-slate-500">{icon}</span>}
            <div>
              {title && <h3 className="text-sm font-semibold text-slate-900">{title}</h3>}
              {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
            </div>
          </div>
          {action}
        </div>
      )}
      <div className={noPadding ? '' : 'p-5'}>{children}</div>
    </div>
  )
}
