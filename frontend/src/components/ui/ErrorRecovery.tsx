import { useState } from 'react'
import { AlertTriangle, RefreshCw, Loader2 } from 'lucide-react'
import { api } from '../../services/api'

interface ErrorRecoveryProps {
  ticketId: string
  errorMessage?: string | null
  className?: string
}

/**
 * Reusable error state with a "Reprocess Ticket" button.
 * Shown when a ticket enters the 'error' status at any pipeline stage.
 */
export default function ErrorRecovery({
  ticketId,
  errorMessage,
  className = '',
}: ErrorRecoveryProps) {
  const [reprocessing, setReprocessing] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  const handleReprocess = async () => {
    setReprocessing(true)
    setFeedback(null)
    try {
      await api.reprocessTicket(ticketId)
      setFeedback('Ticket queued for reprocessing. It will start from Stage A extraction.')
    } catch (err) {
      setFeedback(
        `Reprocess failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
      )
    } finally {
      setReprocessing(false)
    }
  }

  return (
    <div className={`rounded-lg border border-red-200 bg-red-50 p-5 space-y-3 ${className}`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-red-800">Processing Error</p>
          {errorMessage && (
            <p className="text-sm text-red-700 mt-1">{errorMessage}</p>
          )}
        </div>
      </div>

      <button
        onClick={handleReprocess}
        disabled={reprocessing}
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-700 bg-white border border-red-300 rounded-lg hover:bg-red-100 disabled:opacity-50 transition-colors"
      >
        {reprocessing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Reprocessing…
          </>
        ) : (
          <>
            <RefreshCw className="h-4 w-4" />
            Reprocess Ticket
          </>
        )}
      </button>

      {feedback && (
        <p className="text-xs text-red-600">{feedback}</p>
      )}
    </div>
  )
}
