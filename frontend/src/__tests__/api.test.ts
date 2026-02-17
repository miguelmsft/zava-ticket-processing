/**
 * Tests for the API client (services/api.ts).
 *
 * Uses vi.fn() to mock `globalThis.fetch`.
 */

import { api, ApiError } from '../services/api'

// Helper: mock a successful fetch response
function mockFetch(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
  })
}

// Helper: mock a failed fetch response with JSON body
function mockFetchError(detail: string, status = 400) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    statusText: 'Bad Request',
    json: () => Promise.resolve({ detail }),
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
})

// ─── ApiError ───────────────────────────────────────────────────

describe('ApiError', () => {
  it('stores status and message', () => {
    const err = new ApiError(409, 'Conflict')
    expect(err).toBeInstanceOf(Error)
    expect(err.status).toBe(409)
    expect(err.message).toBe('Conflict')
    expect(err.name).toBe('ApiError')
  })
})

// ─── createTicket ───────────────────────────────────────────────

describe('api.createTicket', () => {
  it('sends FormData and returns response', async () => {
    const payload = { ticketId: 'abc', message: 'ok' }
    globalThis.fetch = mockFetch(payload)

    const fd = new FormData()
    fd.append('title', 'Test')
    const result = await api.createTicket(fd)

    expect(result).toEqual(payload)
    expect(fetch).toHaveBeenCalledWith('/api/tickets', {
      method: 'POST',
      body: fd,
    })
  })

  it('throws ApiError on failure', async () => {
    globalThis.fetch = mockFetchError('bad data', 422)

    await expect(api.createTicket(new FormData())).rejects.toThrow(ApiError)
    await expect(api.createTicket(new FormData())).rejects.toMatchObject({
      status: 422,
      message: 'bad data',
    })
  })
})

// ─── listTickets ────────────────────────────────────────────────

describe('api.listTickets', () => {
  it('calls correct URL with defaults', async () => {
    const body = { tickets: [], total: 0, page: 1, pageSize: 50, totalPages: 0 }
    globalThis.fetch = mockFetch(body)

    const result = await api.listTickets()
    expect(result).toEqual(body)

    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    expect(url).toContain('page=1')
    expect(url).toContain('page_size=50')
  })

  it('includes status filter', async () => {
    globalThis.fetch = mockFetch({ tickets: [], total: 0, page: 1, pageSize: 20, totalPages: 0 })

    await api.listTickets(2, 20, 'extracted')

    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=20')
    expect(url).toContain('status=extracted')
  })
})

// ─── getTicket ──────────────────────────────────────────────────

describe('api.getTicket', () => {
  it('fetches single ticket by id', async () => {
    const ticket = { id: 'T-001', status: 'ingested' }
    globalThis.fetch = mockFetch(ticket)

    const result = await api.getTicket('T-001')
    expect(result).toEqual(ticket)

    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    expect(url).toBe('/api/tickets/T-001')
  })

  it('throws on 404', async () => {
    globalThis.fetch = mockFetchError('not found', 404)
    await expect(api.getTicket('nope')).rejects.toThrow(ApiError)
  })
})

// ─── triggerAIProcessing ────────────────────────────────────────

describe('api.triggerAIProcessing', () => {
  it('sends POST and returns', async () => {
    const body = { ticketId: 'T-001', message: 'triggered' }
    globalThis.fetch = mockFetch(body)

    const result = await api.triggerAIProcessing('T-001')
    expect(result).toEqual(body)

    const [url, opts] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe('/api/tickets/T-001/process-ai')
    expect(opts.method).toBe('POST')
  })
})

// ─── triggerInvoiceProcessing ───────────────────────────────────

describe('api.triggerInvoiceProcessing', () => {
  it('sends POST and returns', async () => {
    const body = { ticketId: 'T-001', message: 'triggered' }
    globalThis.fetch = mockFetch(body)

    const result = await api.triggerInvoiceProcessing('T-001')
    expect(result).toEqual(body)

    const [url, opts] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe('/api/tickets/T-001/process-invoice')
    expect(opts.method).toBe('POST')
  })
})

// ─── reprocessTicket ────────────────────────────────────────────

describe('api.reprocessTicket', () => {
  it('sends POST /reprocess', async () => {
    const body = { ticketId: 'T-001', message: 'reprocessing' }
    globalThis.fetch = mockFetch(body)

    await api.reprocessTicket('T-001')

    const [url, opts] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe('/api/tickets/T-001/reprocess')
    expect(opts.method).toBe('POST')
  })
})

// ─── deleteTicket ───────────────────────────────────────────────

describe('api.deleteTicket', () => {
  it('sends DELETE', async () => {
    globalThis.fetch = mockFetch({ ticketId: 'T-001', message: 'deleted' })

    await api.deleteTicket('T-001')

    const [url, opts] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe('/api/tickets/T-001')
    expect(opts.method).toBe('DELETE')
  })
})

// ─── getDashboardMetrics ────────────────────────────────────────

describe('api.getDashboardMetrics', () => {
  it('fetches dashboard metrics', async () => {
    const metrics = { totalTickets: 10, avgProcessingTimeMs: 200, successRate: 0.95 }
    globalThis.fetch = mockFetch(metrics)

    const result = await api.getDashboardMetrics()
    expect(result).toEqual(metrics)

    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    expect(url).toBe('/api/dashboard/metrics')
  })
})

// ─── healthCheck ────────────────────────────────────────────────

describe('api.healthCheck', () => {
  it('fetches /health', async () => {
    globalThis.fetch = mockFetch({ status: 'healthy', dependencies: {} })

    const result = await api.healthCheck()
    expect(result.status).toBe('healthy')

    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    expect(url).toBe('/health')
  })
})

// ─── Error handling edge cases ──────────────────────────────────

describe('error edge cases', () => {
  it('falls back to statusText when JSON parse fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new SyntaxError('Unexpected token')),
    })

    await expect(api.getTicket('bad')).rejects.toMatchObject({
      status: 500,
      message: 'Internal Server Error',
    })
  })
})
