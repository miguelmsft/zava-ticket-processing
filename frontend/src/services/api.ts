import type {
  TicketCreateResponse,
  TicketListResponse,
  TicketDocument,
  DashboardMetrics,
} from '../types/ticket'

// ─── API Base URL ───────────────────────────────────────────────
// In development: empty string → relative URLs proxied by Vite dev server
// In production: set VITE_API_BASE_URL to the backend Container App URL
//   e.g., https://zava-backend.azurecontainerapps.io
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// ─── Error Class ────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

// ─── Internal Helpers ───────────────────────────────────────────

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, options)
  if (!response.ok) {
    let detail: string
    try {
      const body = await response.json()
      detail = body.detail || response.statusText
    } catch {
      detail = response.statusText
    }
    throw new ApiError(response.status, detail)
  }
  return response.json()
}

// ─── Public API Client ──────────────────────────────────────────

export const api = {
  // ── Tickets ──────────────────────────────────────────
  createTicket: async (formData: FormData): Promise<TicketCreateResponse> => {
    const response = await fetch(`${API_BASE}/api/tickets`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      let detail: string
      try {
        const body = await response.json()
        detail = body.detail || response.statusText
      } catch {
        detail = response.statusText
      }
      throw new ApiError(response.status, detail)
    }
    return response.json()
  },

  listTickets: (page = 1, pageSize = 50, status?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (status) params.set('status', status)
    return request<TicketListResponse>(`/api/tickets?${params}`)
  },

  getTicket: (ticketId: string) =>
    request<TicketDocument>(`/api/tickets/${ticketId}`),

  triggerAIProcessing: (ticketId: string) =>
    request<{ ticketId: string; message: string }>(
      `/api/tickets/${ticketId}/process-ai`,
      { method: 'POST' },
    ),

  triggerInvoiceProcessing: (ticketId: string) =>
    request<{ ticketId: string; message: string }>(
      `/api/tickets/${ticketId}/process-invoice`,
      { method: 'POST' },
    ),

  reprocessTicket: (ticketId: string) =>
    request<{ ticketId: string; message: string }>(
      `/api/tickets/${ticketId}/reprocess`,
      { method: 'POST' },
    ),

  deleteTicket: (ticketId: string) =>
    request<{ ticketId: string; message: string }>(
      `/api/tickets/${ticketId}`,
      { method: 'DELETE' },
    ),

  // ── Dashboard ────────────────────────────────────────
  getDashboardMetrics: () =>
    request<DashboardMetrics>('/api/dashboard/metrics'),

  // ── Health ───────────────────────────────────────────
  healthCheck: () =>
    request<{ status: string; dependencies: Record<string, string> }>('/health'),
}
