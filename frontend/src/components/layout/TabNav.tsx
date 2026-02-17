import { useState, useEffect, useCallback } from 'react'
import { ChevronDown, Ticket } from 'lucide-react'
import { cn } from '../../lib/utils'
import { api } from '../../services/api'
import Badge from '../ui/Badge'
import type { TicketSummary } from '../../types/ticket'

interface TabNavProps {
  tabs: string[]
  activeTab: number
  onTabChange: (index: number) => void
  selectedTicketId: string | null
  onTicketSelect: (ticketId: string) => void
  showTicketSelector: boolean
  refreshTrigger: number
}

export default function TabNav({
  tabs,
  activeTab,
  onTabChange,
  selectedTicketId,
  onTicketSelect,
  showTicketSelector,
  refreshTrigger,
}: TabNavProps) {
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const loadTickets = useCallback(async () => {
    try {
      const response = await api.listTickets(1, 50)
      setTickets(response.tickets)
    } catch {
      // Silently fail — backend may not be running yet
    }
  }, [])

  useEffect(() => {
    loadTickets()
  }, [loadTickets, refreshTrigger])

  // Close dropdown on Escape key
  useEffect(() => {
    if (!dropdownOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDropdownOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [dropdownOpen])

  const selectedTicket = tickets.find((t) => t.ticket_id === selectedTicketId)

  return (
    <div className="bg-white border-b border-slate-200 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          {/* Tab buttons */}
          <nav className="flex gap-0" aria-label="Pipeline stages" role="tablist">
            {tabs.map((tab, index) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === index}
                onClick={() => onTabChange(index)}
                className={cn(
                  'px-4 py-3.5 text-sm font-medium border-b-2 transition-all duration-200 whitespace-nowrap',
                  activeTab === index
                    ? 'border-indigo-600 text-indigo-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300 hover:bg-indigo-50/40',
                )}
              >
                <span className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      'inline-flex items-center justify-center h-5 w-5 rounded-full text-[10px] font-bold',
                      activeTab === index
                        ? 'bg-indigo-100 text-indigo-700'
                        : 'bg-slate-100 text-slate-500',
                    )}
                  >
                    {index + 1}
                  </span>
                  {tab}
                </span>
              </button>
            ))}
          </nav>

          {/* Ticket selector */}
          {showTicketSelector && (
            <div className="relative">
              <button
                onClick={() => {
                  if (!dropdownOpen) loadTickets()
                  setDropdownOpen(!dropdownOpen)
                }}
                className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors min-w-[280px]"
              >
                <Ticket className="h-4 w-4 text-slate-400" />
                {selectedTicket ? (
                  <span className="flex-1 text-left truncate">
                    <span className="font-mono text-xs text-slate-500">
                      {selectedTicket.ticket_id}
                    </span>
                    <span className="ml-2 text-slate-700 truncate">
                      {selectedTicket.title.slice(0, 30)}…
                    </span>
                  </span>
                ) : (
                  <span className="flex-1 text-left text-slate-400">Select a ticket…</span>
                )}
                <ChevronDown className="h-4 w-4 text-slate-400" />
              </button>

              {dropdownOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setDropdownOpen(false)}
                  />
                  <div className="absolute right-0 mt-1 w-[420px] max-h-72 overflow-auto bg-white border border-slate-200 rounded-lg shadow-lg z-20">
                    {tickets.length === 0 ? (
                      <p className="px-4 py-3 text-sm text-slate-500">
                        No tickets yet. Submit one in Tab 1.
                      </p>
                    ) : (
                      tickets.map((t) => (
                        <button
                          key={t.ticket_id}
                          onClick={() => {
                            onTicketSelect(t.ticket_id)
                            setDropdownOpen(false)
                          }}
                          className={cn(
                            'w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-50 transition-colors border-b border-slate-100 last:border-0',
                            selectedTicketId === t.ticket_id && 'bg-indigo-50',
                          )}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs text-slate-500">
                                {t.ticket_id}
                              </span>
                              <Badge variant="status" value={t.status} />
                            </div>
                            <p className="text-sm text-slate-700 truncate mt-0.5">{t.title}</p>
                          </div>
                          <Badge variant="priority" value={t.priority} />
                        </button>
                      ))
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
