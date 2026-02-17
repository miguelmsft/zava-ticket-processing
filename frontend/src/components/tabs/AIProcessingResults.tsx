import { useState } from 'react'
import {
  Brain,
  Tags,
  FileText,
  ArrowRight,
  Loader2,
  Flag,
  AlertTriangle,
  Clock,
  Gauge,
} from 'lucide-react'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import Spinner from '../ui/Spinner'
import ErrorRecovery from '../ui/ErrorRecovery'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import {
  formatMs,
  statusLabel,
  nextActionLabel,
  nextActionColor,
} from '../../lib/utils'
import type { TicketDocument } from '../../types/ticket'

interface AIProcessingResultsProps {
  ticketId: string | null
  onTriggerInvoice: (ticketId: string) => void
}

export default function AIProcessingResults({
  ticketId,
  onTriggerInvoice,
}: AIProcessingResultsProps) {
  const [triggeringAI, setTriggeringAI] = useState(false)
  const [triggeringInvoice, setTriggeringInvoice] = useState(false)

  const { data: ticket, error, loading } = usePolling<TicketDocument>(
    ticketId,
    () => api.getTicket(ticketId!),
    3000,
  )

  const handleTriggerAI = async () => {
    if (!ticketId) return
    setTriggeringAI(true)
    try {
      await api.triggerAIProcessing(ticketId)
    } catch {
      // Will be visible on next poll
    } finally {
      setTriggeringAI(false)
    }
  }

  const handleTriggerInvoice = async () => {
    if (!ticketId) return
    setTriggeringInvoice(true)
    try {
      await api.triggerInvoiceProcessing(ticketId)
      onTriggerInvoice(ticketId)
    } catch {
      // Will be visible on next poll
    } finally {
      setTriggeringInvoice(false)
    }
  }

  // ── Empty / Loading / Error ─────────────────────────
  if (!ticketId) {
    return (
      <div className="text-center py-16">
        <Brain className="h-12 w-12 text-slate-300 mx-auto mb-3" />
        <p className="text-slate-500">Select a ticket to view AI processing results</p>
        <p className="text-sm text-slate-400 mt-1">
          The AI agent standardizes codes, creates summaries, and assigns actions.
        </p>
      </div>
    )
  }
  if (loading && !ticket) {
    return (
      <div className="flex justify-center py-16">
        <Spinner label="Loading AI processing results…" />
      </div>
    )
  }
  if (error && !ticket) {
    return (
      <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        {error}
      </div>
    )
  }
  if (!ticket) return null

  const { aiProcessing: ai, status } = ticket
  const isAIProcessing = status === 'ai_processing'
  const canTriggerAI = status === 'extracted'
  const canTriggerInvoice =
    status === 'ai_processed' && ai?.nextAction === 'invoice_processing'
  const codes = ai?.standardizedCodes

  return (
    <div className="space-y-6">
      {/* Status Banner */}
      <div className="flex items-center justify-between p-4 bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/80 shadow-soft">
        <div className="flex items-center gap-4">
          <Badge variant="status" value={status} label={statusLabel(status)} />
          <span className="text-sm text-slate-600">{ticket.raw?.title || ticketId}</span>
        </div>
        {ai?.processingTimeMs > 0 && (
          <span className="text-xs text-slate-500">
            AI Processing: {formatMs(ai.processingTimeMs)}
          </span>
        )}
      </div>

      {/* Not yet triggered */}
      {canTriggerAI && (
        <div className="text-center py-12 space-y-4">
          <Brain className="h-16 w-16 text-slate-300 mx-auto" />
          <div>
            <p className="text-slate-600 font-medium">AI Processing not yet started</p>
            <p className="text-sm text-slate-400 mt-1">
              Extraction is complete. Click below to start the AI Information Processing agent.
            </p>
          </div>
          <button
            onClick={handleTriggerAI}
            disabled={triggeringAI}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white font-medium text-sm rounded-lg hover:bg-indigo-700 hover:shadow-soft-lg active:scale-[0.98] disabled:opacity-50 transition-all duration-150"
          >
            {triggeringAI ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Triggering…
              </>
            ) : (
              <>
                <Brain className="h-4 w-4" />
                Trigger AI Processing
              </>
            )}
          </button>
        </div>
      )}

      {/* Processing spinner */}
      {isAIProcessing && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" label="AI agent is processing — standardizing codes, creating summary…" />
        </div>
      )}

      {/* AI Processing complete */}
      {ai && ai.status !== 'pending' && !isAIProcessing && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Summary */}
          {ai.summary && (
            <div className="lg:col-span-2">
              <Card title="AI Summary" icon={<FileText className="h-4 w-4" />} accent="violet">
                <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
                  {ai.summary}
                </p>
              </Card>
            </div>
          )}

          {/* Next Action */}
          {ai.nextAction && (
            <Card title="Assigned Next Action" icon={<ArrowRight className="h-4 w-4" />} accent="violet">
              <div className="flex items-center gap-3">
                <span
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium ${nextActionColor(ai.nextAction)}`}
                >
                  {nextActionLabel(ai.nextAction)}
                </span>
              </div>
              {ai.nextAction !== 'invoice_processing' && (
                <p className="text-xs text-amber-700 mt-3 p-2 bg-amber-50 rounded-lg">
                  ⚠️ This ticket will not proceed to automated invoice processing. It
                  requires{' '}
                  {ai.nextAction === 'manual_review'
                    ? 'manual review by a supervisor'
                    : ai.nextAction === 'vendor_approval'
                      ? 'vendor approval before payment'
                      : 'budget approval before processing'}
                  .
                </p>
              )}
            </Card>
          )}

          {/* Standardized Codes */}
          {codes && (
            <Card title="Standardized Codes" icon={<Tags className="h-4 w-4" />} accent="violet">
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-500">Vendor Code</dt>
                  <dd className="font-mono text-slate-900">{codes.vendorCode || '—'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Department</dt>
                  <dd className="font-mono text-slate-900">{codes.departmentCode || '—'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Cost Center</dt>
                  <dd className="font-mono text-slate-900">{codes.costCenter || '—'}</dd>
                </div>
                {codes.productCodes && codes.productCodes.length > 0 && (
                  <div>
                    <dt className="text-slate-500 mb-1">Product Codes</dt>
                    <dd className="flex flex-wrap gap-1.5">
                      {codes.productCodes.map((code, i) => (
                        <span
                          key={i}
                          className="inline-flex px-2 py-0.5 bg-slate-100 rounded text-xs font-mono text-slate-700"
                        >
                          {code}
                        </span>
                      ))}
                    </dd>
                  </div>
                )}
              </dl>
            </Card>
          )}

          {/* Flags */}
          {ai.flags && ai.flags.length > 0 && (
            <Card title="Flags" icon={<Flag className="h-4 w-4" />} accent="amber">
              <div className="flex flex-wrap gap-2">
                {ai.flags.map((flag, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800"
                  >
                    <AlertTriangle className="h-3 w-3" />
                    {flag.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </Card>
          )}

          {/* Processing Metadata */}
          <Card title="Processing Metadata" icon={<Clock className="h-4 w-4" />} accent="violet">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-slate-500">Agent</dt>
                <dd className="text-slate-900">{ai.agentName || '—'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Version</dt>
                <dd className="text-slate-900">{ai.agentVersion || '—'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Processing Time</dt>
                <dd className="text-slate-900">{formatMs(ai.processingTimeMs)}</dd>
              </div>
              {ai.confidence > 0 && (
                <div className="flex justify-between items-center">
                  <dt className="text-slate-500 flex items-center gap-1">
                    <Gauge className="h-3.5 w-3.5" />
                    Confidence
                  </dt>
                  <dd className="text-slate-900 font-medium">
                    {Math.round(ai.confidence * 100)}%
                  </dd>
                </div>
              )}
            </dl>
          </Card>

          {/* Error */}
          {ai.errorMessage && (
            <div className="lg:col-span-2 flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {ai.errorMessage}
            </div>
          )}

          {/* Error Recovery */}
          {status === 'error' && ticketId && (
            <div className="lg:col-span-2">
              <ErrorRecovery ticketId={ticketId} errorMessage={ai.errorMessage} />
            </div>
          )}

          {/* Next Step: Invoice Processing */}
          {canTriggerInvoice && (
            <div className="lg:col-span-2">
              <button
                onClick={handleTriggerInvoice}
                disabled={triggeringInvoice}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 text-white font-medium text-sm rounded-lg hover:bg-indigo-700 hover:shadow-soft-lg active:scale-[0.98] disabled:opacity-50 transition-all duration-150"
              >
                {triggeringInvoice ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Triggering Invoice Processing…
                  </>
                ) : (
                  <>
                    Next: Invoice Processing
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
