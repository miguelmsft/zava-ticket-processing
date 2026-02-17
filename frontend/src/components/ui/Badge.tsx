import { cn } from '../../lib/utils'

const STATUS_STYLES: Record<string, string> = {
  ingested: 'bg-blue-100 text-blue-800',
  extracting: 'bg-amber-100 text-amber-800 animate-pulse',
  extracted: 'bg-teal-100 text-teal-800',
  ai_processing: 'bg-violet-100 text-violet-800 animate-pulse',
  ai_processed: 'bg-indigo-100 text-indigo-800',
  invoice_processing: 'bg-orange-100 text-orange-800 animate-pulse',
  invoice_processed: 'bg-emerald-100 text-emerald-800',
  error: 'bg-red-100 text-red-800',
  pending: 'bg-slate-100 text-slate-600',
  completed: 'bg-emerald-100 text-emerald-800',
  skipped: 'bg-slate-100 text-slate-600',
}

const PRIORITY_STYLES: Record<string, string> = {
  normal: 'bg-slate-100 text-slate-700',
  high: 'bg-orange-100 text-orange-800',
  urgent: 'bg-red-100 text-red-800',
}

interface BadgeProps {
  variant?: 'status' | 'priority' | 'custom'
  value: string
  label?: string
  className?: string
}

export default function Badge({ variant = 'status', value, label, className }: BadgeProps) {
  const styles =
    variant === 'priority'
      ? PRIORITY_STYLES[value] || 'bg-slate-100 text-slate-700'
      : STATUS_STYLES[value] || 'bg-slate-100 text-slate-700'

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        styles,
        className,
      )}
    >
      {label || value.replace(/_/g, ' ')}
    </span>
  )
}
