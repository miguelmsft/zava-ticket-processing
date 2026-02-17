import { useState, useEffect, useCallback, useRef } from 'react'
import {
  BarChart3,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Timer,
  CreditCard,
  ClipboardList,
  RefreshCw,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import Spinner from '../ui/Spinner'
import { api } from '../../services/api'
import { formatMs, statusLabel, timeAgo } from '../../lib/utils'
import type { DashboardMetrics, TicketSummary } from '../../types/ticket'

const STATUS_COLORS: Record<string, string> = {
  ingested: '#3b82f6',
  extracting: '#f59e0b',
  extracted: '#14b8a6',
  ai_processing: '#8b5cf6',
  ai_processed: '#6366f1',
  invoice_processing: '#f97316',
  invoice_processed: '#10b981',
  error: '#ef4444',
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      const [metricsRes, ticketsRes] = await Promise.all([
        api.getDashboardMetrics(),
        api.listTickets(1, 10),
      ])
      setMetrics(metricsRes)
      setTickets(ticketsRes.tickets)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading && !metrics) {
    return (
      <div className="flex justify-center py-16">
        <Spinner label="Loading dashboard…" />
      </div>
    )
  }

  if (error && !metrics) {
    return (
      <div className="text-center py-16 space-y-4">
        <AlertTriangle className="h-12 w-12 text-slate-300 mx-auto" />
        <p className="text-slate-500">Could not load dashboard data</p>
        <p className="text-sm text-slate-400">{error}</p>
        <button
          onClick={fetchData}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    )
  }

  // Build pipeline chart data
  const pipelineData = metrics
    ? Object.entries(metrics.tickets_by_status)
        .filter(([, count]) => count > 0)
        .map(([status, count]) => ({
          name: statusLabel(status),
          count,
          fill: STATUS_COLORS[status] || '#94a3b8',
        }))
    : []

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        <MetricCard
          label="Total Tickets"
          value={metrics?.total_tickets ?? 0}
          icon={<ClipboardList className="h-5 w-5" />}
          color="indigo"
        />
        <div className="bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/80 shadow-soft p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Success Rate
            </span>
            <span className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">
              <TrendingUp className="h-5 w-5" />
            </span>
          </div>
          <div className="flex items-center gap-3 mt-2">
            <ProgressRing
              percent={Math.round((metrics?.success_rate ?? 0) * 100)}
              size={48}
              strokeWidth={5}
            />
            <AnimatedValue
              value={Math.round((metrics?.success_rate ?? 0) * 100)}
              suffix="%"
              className="text-2xl font-bold text-slate-900"
            />
          </div>
        </div>
        <MetricCard
          label="Payments Submitted"
          value={metrics?.payment_submitted_count ?? 0}
          icon={<CreditCard className="h-5 w-5" />}
          color="blue"
        />
        <MetricCard
          label="Errors"
          value={metrics?.error_count ?? 0}
          icon={<AlertTriangle className="h-5 w-5" />}
          color="red"
        />
      </div>

      {/* Processing Times */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        <TimeCard label="Avg Extraction" value={metrics?.avg_extraction_time_ms} />
        <TimeCard label="Avg AI Processing" value={metrics?.avg_ai_processing_time_ms} />
        <TimeCard label="Avg Invoice Processing" value={metrics?.avg_invoice_processing_time_ms} />
        <TimeCard label="Avg Total Pipeline" value={metrics?.avg_total_pipeline_time_ms} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 stagger-children">
        {/* Pipeline Chart */}
        <Card
          title="Pipeline Status"
          subtitle="Tickets by processing stage"
          icon={<BarChart3 className="h-4 w-4" />}
        >
          {pipelineData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={pipelineData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  interval={0}
                  angle={-20}
                  textAnchor="end"
                  height={60}
                />
                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    borderRadius: '0.5rem',
                    border: '1px solid #e2e8f0',
                    fontSize: '0.8rem',
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {pipelineData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
              No ticket data to display
            </div>
          )}
        </Card>

        {/* Recent Tickets */}
        <Card
          title="Recent Tickets"
          subtitle={`${tickets.length} most recent`}
          icon={<ClipboardList className="h-4 w-4" />}
          noPadding
        >
          {tickets.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {tickets.map((t) => (
                <div
                  key={t.ticket_id}
                  className="flex items-center justify-between px-5 py-3 hover:bg-slate-50/50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-500">
                        {t.ticket_id}
                      </span>
                      <Badge variant="priority" value={t.priority} />
                    </div>
                    <p className="text-sm text-slate-700 truncate mt-0.5">{t.title}</p>
                  </div>
                  <div className="flex items-center gap-3 ml-4">
                    <Badge variant="status" value={t.status} />
                    {t.created_at && (
                      <span className="text-xs text-slate-400 whitespace-nowrap">
                        {timeAgo(t.created_at)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
              No tickets yet — submit one in Tab 1
            </div>
          )}
        </Card>
      </div>

      {/* Additional Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 stagger-children">
        <MetricCard
          label="Manual Reviews"
          value={metrics?.manual_review_count ?? 0}
          icon={<CheckCircle2 className="h-5 w-5" />}
          color="amber"
        />
        <MetricCard
          label="Processed Today"
          value={metrics?.tickets_processed_today ?? 0}
          icon={<Timer className="h-5 w-5" />}
          color="teal"
        />
        <MetricCard
          label="Pipeline Stages"
          value={Object.keys(metrics?.tickets_by_status ?? {}).length}
          icon={<BarChart3 className="h-5 w-5" />}
          color="slate"
        />
      </div>
    </div>
  )
}

// ─── Hooks ──────────────────────────────────────────────────

function useCountUp(target: number, duration = 800): number {
  const [current, setCurrent] = useState(0)
  const prevTarget = useRef(target)
  const currentRef = useRef(0)

  // Keep currentRef in sync with state
  currentRef.current = current

  useEffect(() => {
    if (target === prevTarget.current && currentRef.current !== 0) return
    const startValue = prevTarget.current !== target ? currentRef.current : 0
    prevTarget.current = target
    if (target === 0) { setCurrent(0); return }

    const start = performance.now()
    let raf: number
    const step = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setCurrent(Math.round(startValue + eased * (target - startValue)))
      if (progress < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, duration]) // eslint-disable-line react-hooks/exhaustive-deps

  return current
}

// ─── Sub-components ─────────────────────────────────────────────

const COLOR_MAP: Record<string, string> = {
  indigo: 'bg-indigo-50 text-indigo-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  blue: 'bg-blue-50 text-blue-600',
  red: 'bg-red-50 text-red-600',
  amber: 'bg-amber-50 text-amber-600',
  teal: 'bg-teal-50 text-teal-600',
  slate: 'bg-slate-100 text-slate-600',
}

function AnimatedValue({
  value,
  suffix = '',
  className = '',
}: {
  value: number
  suffix?: string
  className?: string
}) {
  const animated = useCountUp(value)
  return <p className={className}>{animated}{suffix}</p>
}

function MetricCard({
  label,
  value,
  icon,
  color,
}: {
  label: string
  value: number | string
  icon: React.ReactNode
  color: string
}) {
  const numericValue = typeof value === 'number' ? value : null
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/80 shadow-soft p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
          {label}
        </span>
        <span className={`p-1.5 rounded-lg ${COLOR_MAP[color] || COLOR_MAP.slate}`}>
          {icon}
        </span>
      </div>
      {numericValue !== null ? (
        <AnimatedValue value={numericValue} className="text-2xl font-bold text-slate-900 mt-2" />
      ) : (
        <p className="text-2xl font-bold text-slate-900 mt-2">{value}</p>
      )}
    </div>
  )
}

function TimeCard({
  label,
  value,
}: {
  label: string
  value: number | undefined
}) {
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/80 shadow-soft p-4">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
        {label}
      </span>
      <p className="text-lg font-semibold text-slate-900 mt-1 flex items-center gap-1.5">
        <Timer className="h-4 w-4 text-slate-400" />
        {formatMs(value)}
      </p>
    </div>
  )
}

function ProgressRing({
  percent,
  size = 48,
  strokeWidth = 5,
}: {
  percent: number
  size?: number
  strokeWidth?: number
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const [offset, setOffset] = useState(circumference)

  useEffect(() => {
    // Trigger animation after mount
    const timer = setTimeout(() => {
      setOffset(circumference - (percent / 100) * circumference)
    }, 100)
    return () => clearTimeout(timer)
  }, [percent, circumference])

  const color =
    percent >= 80 ? '#10b981' : percent >= 50 ? '#f59e0b' : '#ef4444'

  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#e2e8f0"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className="progress-ring-circle"
      />
    </svg>
  )
}
