/**
 * Tests for utility functions (lib/utils.ts).
 *
 * Covers all formatting helpers, status labels, and processing checks.
 */

import {
  cn,
  formatDate,
  formatDateShort,
  formatCurrency,
  formatMs,
  formatBytes,
  statusLabel,
  nextActionLabel,
  nextActionColor,
  timeAgo,
  isProcessing,
} from '../lib/utils'

// ─── cn (className merger) ──────────────────────────────────────

describe('cn', () => {
  it('merges strings', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('handles conditional classes', () => {
    expect(cn('base', false && 'hidden', 'extra')).toBe('base extra')
  })

  it('returns empty for no args', () => {
    expect(cn()).toBe('')
  })
})

// ─── formatDate ─────────────────────────────────────────────────

describe('formatDate', () => {
  it('returns — for null', () => {
    expect(formatDate(null)).toBe('—')
  })

  it('returns — for undefined', () => {
    expect(formatDate(undefined)).toBe('—')
  })

  it('formats a valid ISO string', () => {
    const result = formatDate('2026-01-22T10:30:00Z')
    expect(result).toContain('2026')
    expect(result).toContain('Jan')
  })
})

// ─── formatDateShort ────────────────────────────────────────────

describe('formatDateShort', () => {
  it('returns — for null', () => {
    expect(formatDateShort(null)).toBe('—')
  })

  it('formats date without time', () => {
    const result = formatDateShort('2026-01-22T10:30:00Z')
    expect(result).toContain('2026')
  })
})

// ─── formatCurrency ─────────────────────────────────────────────

describe('formatCurrency', () => {
  it('returns — for null', () => {
    expect(formatCurrency(null)).toBe('—')
  })

  it('returns — for undefined', () => {
    expect(formatCurrency(undefined)).toBe('—')
  })

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('formats large amounts with commas', () => {
    const result = formatCurrency(13531.25)
    expect(result).toContain('13,531.25')
  })
})

// ─── formatMs ───────────────────────────────────────────────────

describe('formatMs', () => {
  it('returns — for null', () => {
    expect(formatMs(null)).toBe('—')
  })

  it('returns — for zero', () => {
    expect(formatMs(0)).toBe('—')
  })

  it('formats ms under 1000', () => {
    expect(formatMs(750)).toBe('750ms')
  })

  it('formats ms over 1000 as seconds', () => {
    expect(formatMs(3200)).toBe('3.2s')
  })
})

// ─── formatBytes ────────────────────────────────────────────────

describe('formatBytes', () => {
  it('returns — for null', () => {
    expect(formatBytes(null)).toBe('—')
  })

  it('formats bytes', () => {
    expect(formatBytes(500)).toBe('500 B')
  })

  it('formats KB', () => {
    expect(formatBytes(45000)).toBe('43.9 KB')
  })

  it('formats MB', () => {
    expect(formatBytes(2500000)).toBe('2.4 MB')
  })
})

// ─── statusLabel ────────────────────────────────────────────────

describe('statusLabel', () => {
  it('maps known statuses', () => {
    expect(statusLabel('ingested')).toBe('Ingested')
    expect(statusLabel('extracting')).toBe('Extracting…')
    expect(statusLabel('error')).toBe('Error')
    expect(statusLabel('invoice_processed')).toBe('Invoice Processed')
  })

  it('returns raw string for unknown', () => {
    expect(statusLabel('custom_status')).toBe('custom_status')
  })
})

// ─── nextActionLabel ────────────────────────────────────────────

describe('nextActionLabel', () => {
  it('maps known actions', () => {
    expect(nextActionLabel('invoice_processing')).toBe('Route to Invoice Processing')
    expect(nextActionLabel('manual_review')).toBe('Route to Manual Review')
  })

  it('returns — for null', () => {
    expect(nextActionLabel(null)).toBe('—')
  })

  it('returns — for undefined', () => {
    expect(nextActionLabel(undefined)).toBe('—')
  })
})

// ─── nextActionColor ────────────────────────────────────────────

describe('nextActionColor', () => {
  it('returns emerald for invoice_processing', () => {
    expect(nextActionColor('invoice_processing')).toContain('emerald')
  })

  it('returns amber for other actions', () => {
    expect(nextActionColor('manual_review')).toContain('amber')
  })

  it('returns slate for null', () => {
    expect(nextActionColor(null)).toContain('slate')
  })
})

// ─── timeAgo ────────────────────────────────────────────────────

describe('timeAgo', () => {
  it('returns "Just now" for recent dates', () => {
    expect(timeAgo(new Date().toISOString())).toBe('Just now')
  })

  it('returns minutes for recent past', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    expect(timeAgo(fiveMinAgo)).toBe('5m ago')
  })

  it('returns hours for older', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
    expect(timeAgo(twoHoursAgo)).toBe('2h ago')
  })

  it('returns days for much older', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
    expect(timeAgo(threeDaysAgo)).toBe('3d ago')
  })
})

// ─── isProcessing ───────────────────────────────────────────────

describe('isProcessing', () => {
  it('returns true for active stages', () => {
    expect(isProcessing('extracting')).toBe(true)
    expect(isProcessing('ai_processing')).toBe(true)
    expect(isProcessing('invoice_processing')).toBe(true)
  })

  it('returns false for completed/idle stages', () => {
    expect(isProcessing('ingested')).toBe(false)
    expect(isProcessing('extracted')).toBe(false)
    expect(isProcessing('invoice_processed')).toBe(false)
    expect(isProcessing('error')).toBe(false)
  })
})
