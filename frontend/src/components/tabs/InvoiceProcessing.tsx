import { useState } from 'react'
import {
  Receipt,
  CheckCircle2,
  XCircle,
  CreditCard,
  AlertTriangle,
  Loader2,
  Ban,
  Clock,
} from 'lucide-react'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import Spinner from '../ui/Spinner'
import ErrorRecovery from '../ui/ErrorRecovery'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import {
  formatDate,
  formatMs,
  statusLabel,
  nextActionLabel,
} from '../../lib/utils'
import type { TicketDocument, InvoiceValidations } from '../../types/ticket'

interface InvoiceProcessingProps {
  ticketId: string | null
}

export default function InvoiceProcessing({ ticketId }: InvoiceProcessingProps) {
  const [triggering, setTriggering] = useState(false)

  const { data: ticket, error, loading } = usePolling<TicketDocument>(
    ticketId,
    () => api.getTicket(ticketId!),
    3000,
  )

  const handleTrigger = async () => {
    if (!ticketId) return
    setTriggering(true)
    try {
      await api.triggerInvoiceProcessing(ticketId)
    } catch {
      // Will be visible on next poll
    } finally {
      setTriggering(false)
    }
  }

  // ── Empty / Loading / Error ─────────────────────────
  if (!ticketId) {
    return (
      <div className="text-center py-16">
        <Receipt className="h-12 w-12 text-slate-300 mx-auto mb-3" />
        <p className="text-slate-500">Select a ticket to view invoice processing results</p>
        <p className="text-sm text-slate-400 mt-1">
          The invoice agent validates and submits payments.
        </p>
      </div>
    )
  }
  if (loading && !ticket) {
    return (
      <div className="flex justify-center py-16">
        <Spinner label="Loading invoice processing results…" />
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

  const { invoiceProcessing: inv, aiProcessing: ai, status } = ticket
  const isProcessing = status === 'invoice_processing'
  const canTrigger = status === 'ai_processed'
  const isRouted =
    ai?.nextAction && ai.nextAction !== 'invoice_processing'
  const validations = inv?.validations
  const payment = inv?.paymentSubmission

  return (
    <div className="space-y-6">
      {/* Status Banner */}
      <div className="flex items-center justify-between p-4 bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/80 shadow-soft">
        <div className="flex items-center gap-4">
          <Badge variant="status" value={status} label={statusLabel(status)} />
          <span className="text-sm text-slate-600">{ticket.raw?.title || ticketId}</span>
        </div>
        {inv?.processingTimeMs > 0 && (
          <span className="text-xs text-slate-500">
            Invoice Processing: {formatMs(inv.processingTimeMs)}
          </span>
        )}
      </div>

      {/* Routed to different action (not invoice processing) */}
      {isRouted && inv?.status === 'pending' && (
        <div className="text-center py-12 space-y-4">
          <Ban className="h-16 w-16 text-amber-400 mx-auto" />
          <div>
            <p className="text-slate-600 font-medium">Invoice Processing Not Applicable</p>
            <p className="text-sm text-slate-400 mt-1">
              This ticket was routed to{' '}
              <span className="font-medium text-amber-700">
                {nextActionLabel(ai?.nextAction)}
              </span>{' '}
              by the AI agent and will not go through automated invoice processing.
            </p>
          </div>
        </div>
      )}

      {/* Not yet triggered */}
      {canTrigger && !isRouted && (
        <div className="text-center py-12 space-y-4">
          <Receipt className="h-16 w-16 text-slate-300 mx-auto" />
          <div>
            <p className="text-slate-600 font-medium">
              Invoice Processing not yet started
            </p>
            <p className="text-sm text-slate-400 mt-1">
              AI processing is complete. Click below to validate the invoice and submit
              payment.
            </p>
          </div>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white font-medium text-sm rounded-lg hover:bg-indigo-700 hover:shadow-soft-lg active:scale-[0.98] disabled:opacity-50 transition-all duration-150"
          >
            {triggering ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Triggering…
              </>
            ) : (
              <>
                <Receipt className="h-4 w-4" />
                Trigger Invoice Processing
              </>
            )}
          </button>
        </div>
      )}

      {/* Processing spinner */}
      {isProcessing && (
        <div className="flex justify-center py-12">
          <Spinner
            size="lg"
            label="Invoice agent is processing — validating invoice, submitting payment…"
          />
        </div>
      )}

      {/* Invoice Processing complete */}
      {inv && inv.status !== 'pending' && !isProcessing && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Validation Checklist */}
          {validations && (
            <Card title="Validation Checklist" icon={<CheckCircle2 className="h-4 w-4" />} accent="emerald">
              <div className="space-y-2">
                <ValidationRow
                  label="Invoice Number Valid"
                  value={validations.invoiceNumberValid}
                />
                <ValidationRow
                  label="Amount Correct"
                  value={validations.amountCorrect}
                />
                <ValidationRow
                  label="Due Date Valid"
                  value={validations.dueDateValid}
                />
                <ValidationRow
                  label="Vendor Approved"
                  value={validations.vendorApproved}
                />
                <ValidationRow
                  label="Budget Available"
                  value={validations.budgetAvailable}
                />
              </div>
            </Card>
          )}

          {/* Payment Submission */}
          {payment && (
            <Card title="Payment Submission" icon={<CreditCard className="h-4 w-4" />} accent="emerald">
              {payment.submitted ? (
                <dl className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Status</dt>
                    <dd>
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded-full text-xs font-medium">
                        <CheckCircle2 className="h-3 w-3" />
                        Submitted
                      </span>
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Payment ID</dt>
                    <dd className="font-mono text-slate-900">{payment.paymentId || '—'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Payment Method</dt>
                    <dd className="text-slate-900">{payment.paymentMethod || '—'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Expected Date</dt>
                    <dd className="text-slate-900">
                      {formatDate(payment.expectedPaymentDate)}
                    </dd>
                  </div>
                  {payment.submittedAt && (
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Submitted At</dt>
                      <dd className="text-slate-900">{formatDate(payment.submittedAt)}</dd>
                    </div>
                  )}
                </dl>
              ) : (
                <div className="flex items-center gap-2 p-3 bg-amber-50 rounded-lg text-sm text-amber-800">
                  <XCircle className="h-4 w-4 shrink-0" />
                  Payment not submitted — validation checks did not pass or the ticket was
                  routed to a different action.
                </div>
              )}
            </Card>
          )}

          {/* Processing Metadata */}
          <Card title="Processing Metadata" icon={<Clock className="h-4 w-4" />} accent="emerald">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-slate-500">Agent</dt>
                <dd className="text-slate-900">{inv.agentName || '—'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Version</dt>
                <dd className="text-slate-900">{inv.agentVersion || '—'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Processing Time</dt>
                <dd className="text-slate-900">{formatMs(inv.processingTimeMs)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Status</dt>
                <dd>
                  <Badge variant="status" value={inv.status} label={statusLabel(inv.status)} />
                </dd>
              </div>
            </dl>
          </Card>

          {/* Errors */}
          {inv.errors && inv.errors.length > 0 && (
            <Card title="Errors" icon={<AlertTriangle className="h-4 w-4" />} accent="amber">
              <div className="space-y-2">
                {inv.errors.map((err, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 p-2 bg-red-50 rounded-lg text-sm text-red-700"
                  >
                    <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    {err}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {inv.errorMessage && (
            <div className="lg:col-span-2 flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {inv.errorMessage}
            </div>
          )}

          {/* Error Recovery */}
          {status === 'error' && ticketId && (
            <div className="lg:col-span-2">
              <ErrorRecovery ticketId={ticketId} errorMessage={inv.errorMessage} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Sub-components ─────────────────────────────────────────────

function ValidationRow({
  label,
  value,
}: {
  label: string
  value: InvoiceValidations[keyof InvoiceValidations]
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0">
      <span className="text-sm text-slate-700">{label}</span>
      {value === true && (
        <span className="flex items-center gap-1 text-emerald-600 text-sm font-medium">
          <CheckCircle2 className="h-4 w-4" />
          Pass
        </span>
      )}
      {value === false && (
        <span className="flex items-center gap-1 text-red-600 text-sm font-medium">
          <XCircle className="h-4 w-4" />
          Fail
        </span>
      )}
      {value === null && (
        <span className="text-xs text-slate-400">—</span>
      )}
    </div>
  )
}
