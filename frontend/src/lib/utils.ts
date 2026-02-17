import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

export function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount)
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null || ms === 0) return '—'
  if (ms < 1000) return `${Math.round(ms * 10) / 10}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    ingested: 'Ingested',
    extracting: 'Extracting…',
    extracted: 'Extracted',
    ai_processing: 'AI Processing…',
    ai_processed: 'AI Processed',
    invoice_processing: 'Invoice Processing…',
    invoice_processed: 'Invoice Processed',
    error: 'Error',
    pending: 'Pending',
    completed: 'Completed',
    skipped: 'Skipped',
  }
  return labels[status] || status
}

export function nextActionLabel(action: string | null | undefined): string {
  const labels: Record<string, string> = {
    invoice_processing: 'Route to Invoice Processing',
    manual_review: 'Route to Manual Review',
    vendor_approval: 'Route to Vendor Approval',
    budget_approval: 'Route to Budget Approval',
  }
  return action ? labels[action] || action : '—'
}

export function nextActionColor(action: string | null | undefined): string {
  if (!action) return 'bg-slate-100 text-slate-700'
  if (action === 'invoice_processing') return 'bg-emerald-100 text-emerald-800'
  return 'bg-amber-100 text-amber-800'
}

export function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

/** True if the ticket is actively being processed by some stage. */
export function isProcessing(status: string): boolean {
  return ['extracting', 'ai_processing', 'invoice_processing'].includes(status)
}
