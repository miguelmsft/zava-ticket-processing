import { useState } from 'react'
import {
  FileSearch,
  FileText,
  Hash,
  DollarSign,
  Package,
  Shield,
  AlertTriangle,
  ArrowRight,
  Loader2,
} from 'lucide-react'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import Spinner from '../ui/Spinner'
import ErrorRecovery from '../ui/ErrorRecovery'
import { usePolling } from '../../hooks/usePolling'
import { api } from '../../services/api'
import {
  formatDate,
  formatCurrency,
  formatMs,
  formatBytes,
  statusLabel,
} from '../../lib/utils'
import type { TicketDocument } from '../../types/ticket'

interface ExtractionResultsProps {
  ticketId: string | null
  onTriggerAI: (ticketId: string) => void
}

export default function ExtractionResults({ ticketId, onTriggerAI }: ExtractionResultsProps) {
  const [triggering, setTriggering] = useState(false)

  const { data: ticket, error, loading } = usePolling<TicketDocument>(
    ticketId,
    () => api.getTicket(ticketId!),
    3000,
  )

  const handleTriggerAI = async () => {
    if (!ticketId) return
    setTriggering(true)
    try {
      await api.triggerAIProcessing(ticketId)
      onTriggerAI(ticketId)
    } catch {
      // Will be visible on next poll
    } finally {
      setTriggering(false)
    }
  }

  // ── Empty / Loading / Error states ──────────────────
  if (!ticketId) {
    return <EmptyState message="Select a ticket to view extraction results" />
  }
  if (loading && !ticket) {
    return (
      <div className="flex justify-center py-16">
        <Spinner label="Loading extraction results…" />
      </div>
    )
  }
  if (error && !ticket) {
    return <ErrorBanner message={error} />
  }
  if (!ticket) return null

  const { extraction, status, raw, attachments } = ticket
  const cu = extraction?.contentUnderstanding
  const meta = extraction?.basicMetadata
  const isExtracting = status === 'extracting' || extraction?.status === 'pending'
  const canTriggerAI = status === 'extracted'

  return (
    <div className="space-y-6">
      {/* Status Banner */}
      <div className="flex items-center justify-between p-4 bg-white/80 backdrop-blur-sm rounded-lg border border-slate-200/80 shadow-soft">
        <div className="flex items-center gap-4">
          <Badge variant="status" value={status} label={statusLabel(status)} />
          <span className="text-sm text-slate-600">{raw?.title || ticketId}</span>
        </div>
        <div className="flex items-center gap-2">
          {extraction?.extractionMethod && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              extraction.extractionMethod === 'cu'
                ? 'bg-violet-100 text-violet-700'
                : 'bg-emerald-100 text-emerald-700'
            }`}>
              {extraction.extractionMethod === 'cu' ? '🧠 Content Understanding' : '⚡ Python Regex'}
            </span>
          )}
          {extraction?.processingTimeMs > 0 && (
            <span className="text-xs text-slate-500">
              Extraction: {formatMs(extraction.processingTimeMs)}
            </span>
          )}
        </div>
      </div>

      {/* Extracting state */}
      {isExtracting && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" label="Extraction in progress — analyzing PDF…" />
        </div>
      )}

      {/* Extraction complete */}
      {!isExtracting && extraction?.status !== 'pending' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Basic Metadata */}
          {meta && (
            <Card title="PDF Metadata" icon={<FileText className="h-4 w-4" />} accent="teal">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Dt>Pages</Dt>
                <Dd>{meta.pageCount}</Dd>
                <Dt>File Size</Dt>
                <Dd>{meta.fileSizeDisplay || formatBytes(meta.fileSizeBytes)}</Dd>
                <Dt>Creation Date</Dt>
                <Dd>{meta.pdfCreationDate || '—'}</Dd>
                <Dt>Attachment</Dt>
                <Dd>{attachments?.[0]?.filename || '—'}</Dd>
              </dl>
            </Card>
          )}

          {/* Invoice Details */}
          {cu && (
            <Card title="Invoice Details" icon={<Hash className="h-4 w-4" />} accent="teal">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Dt>Invoice #</Dt>
                <Dd className="font-mono">{cu.invoiceNumber || '—'}</Dd>
                <Dt>PO Number</Dt>
                <Dd className="font-mono">{cu.poNumber || '—'}</Dd>
                <Dt>Vendor</Dt>
                <Dd>{cu.vendorName || '—'}</Dd>
                <Dt>Invoice Date</Dt>
                <Dd>{formatDate(cu.invoiceDate)}</Dd>
                <Dt>Due Date</Dt>
                <Dd>{formatDate(cu.dueDate)}</Dd>
                <Dt>Payment Terms</Dt>
                <Dd>{cu.paymentTerms || '—'}</Dd>
              </dl>
            </Card>
          )}

          {/* Amounts */}
          {cu && (
            <Card title="Amounts" icon={<DollarSign className="h-4 w-4" />} accent="teal">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Dt>Subtotal</Dt>
                <Dd>{formatCurrency(cu.subtotal)}</Dd>
                <Dt>Tax</Dt>
                <Dd>{formatCurrency(cu.taxAmount)}</Dd>
                {cu.hazmatSurcharge > 0 && (
                  <>
                    <Dt>Hazmat Surcharge</Dt>
                    <Dd>{formatCurrency(cu.hazmatSurcharge)}</Dd>
                  </>
                )}
                <Dt className="font-semibold">Total</Dt>
                <Dd className="font-semibold text-lg">{formatCurrency(cu.totalAmount)}</Dd>
              </dl>
            </Card>
          )}

          {/* Special Flags */}
          {cu && (cu.hazardousFlag || cu.billOfLading) && (
            <Card title="Special Flags" icon={<Shield className="h-4 w-4" />} accent="amber">
              <div className="space-y-2">
                {cu.hazardousFlag && (
                  <div className="flex items-center gap-2 p-2 bg-amber-50 rounded-lg text-sm">
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                    <span className="text-amber-800">
                      Hazardous Materials — {cu.dotClassification}
                    </span>
                  </div>
                )}
                {cu.billOfLading && (
                  <div className="flex items-center gap-2 p-2 bg-blue-50 rounded-lg text-sm">
                    <Package className="h-4 w-4 text-blue-600" />
                    <span className="text-blue-800">Bill of Lading: {cu.billOfLading}</span>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Confidence Scores */}
          {cu?.confidenceScores && (
            <Card title="Confidence Scores" icon={<FileSearch className="h-4 w-4" />} accent="teal">
              <div className="space-y-3">
                {Object.entries(cu.confidenceScores).map(([key, val]) => (
                  <ConfidenceBar key={key} label={key} value={val as number} />
                ))}
              </div>
            </Card>
          )}

          {/* Line Items */}
          {cu && cu.lineItems && cu.lineItems.length > 0 && (
            <div className="lg:col-span-2">
              <Card
                title={`Line Items (${cu.lineItems.length})`}
                icon={<Package className="h-4 w-4" />}
                noPadding
                accent="teal"
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 bg-slate-50/50">
                        <th className="text-left px-5 py-2.5 font-medium text-slate-600">
                          Description
                        </th>
                        <th className="text-left px-5 py-2.5 font-medium text-slate-600">
                          Code
                        </th>
                        <th className="text-right px-5 py-2.5 font-medium text-slate-600">
                          Qty
                        </th>
                        <th className="text-right px-5 py-2.5 font-medium text-slate-600">
                          Unit Price
                        </th>
                        <th className="text-right px-5 py-2.5 font-medium text-slate-600">
                          Amount
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {cu.lineItems.map((item, i) => (
                        <tr
                          key={i}
                          className="border-b border-slate-50 hover:bg-slate-50/50"
                        >
                          <td className="px-5 py-2.5 text-slate-700">{item.description}</td>
                          <td className="px-5 py-2.5 font-mono text-xs text-slate-500">
                            {item.productCode}
                          </td>
                          <td className="px-5 py-2.5 text-right text-slate-700">
                            {item.quantity}
                          </td>
                          <td className="px-5 py-2.5 text-right text-slate-700">
                            {formatCurrency(item.unitPrice)}
                          </td>
                          <td className="px-5 py-2.5 text-right font-medium text-slate-900">
                            {formatCurrency(item.amount)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          {/* Error */}
          {extraction?.errorMessage && (
            <div className="lg:col-span-2">
              <ErrorBanner message={extraction.errorMessage} />
            </div>
          )}

          {/* Error Recovery */}
          {status === 'error' && ticketId && (
            <div className="lg:col-span-2">
              <ErrorRecovery
                ticketId={ticketId}
                errorMessage={extraction?.errorMessage}
              />
            </div>
          )}

          {/* Next Step */}
          {canTriggerAI && (
            <div className="lg:col-span-2">
              <button
                onClick={handleTriggerAI}
                disabled={triggering}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 text-white font-medium text-sm rounded-lg hover:bg-indigo-700 hover:shadow-soft-lg active:scale-[0.98] disabled:opacity-50 transition-all duration-150"
              >
                {triggering ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Triggering AI Processing…
                  </>
                ) : (
                  <>
                    Next: AI Processing
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

// ─── Shared Sub-components ──────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-16">
      <FileSearch className="h-12 w-12 text-slate-300 mx-auto mb-3" />
      <p className="text-slate-500">{message}</p>
      <p className="text-sm text-slate-400 mt-1">
        Submit a ticket in Tab 1 or select one from the dropdown above.
      </p>
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  )
}

function Dt({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return <dt className={`text-slate-500 ${className}`}>{children}</dt>
}

function Dd({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return <dd className={`text-slate-900 ${className}`}>{children}</dd>
}

function ConfidenceBar({ label, value }: { label: string; value: number }) {
  const percent = Math.round(value * 100)
  const color =
    percent >= 80 ? 'bg-emerald-500' : percent >= 50 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-slate-600 capitalize">
          {label.replace(/([A-Z])/g, ' $1').trim()}
        </span>
        <span className="font-medium text-slate-700">{percent}%</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}
