import { useState, useCallback } from 'react'
import Header from './components/layout/Header'
import TabNav from './components/layout/TabNav'
import TicketIngestion from './components/tabs/TicketIngestion'
import ExtractionResults from './components/tabs/ExtractionResults'
import AIProcessingResults from './components/tabs/AIProcessingResults'
import InvoiceProcessing from './components/tabs/InvoiceProcessing'
import Dashboard from './components/tabs/Dashboard'

const TABS = [
  'Ticket Ingestion',
  'Extraction Results',
  'AI Processing',
  'Invoice Processing',
  'Dashboard',
]

export default function App() {
  const [activeTab, setActiveTab] = useState(0)
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // After submission in Tab 1 → select the ticket + switch to Tab 2
  const handleTicketCreated = useCallback((ticketId: string) => {
    setSelectedTicketId(ticketId)
    setRefreshTrigger((prev) => prev + 1)
    setActiveTab(1)
  }, [])

  // After triggering AI from Tab 2 → switch to Tab 3
  const handleTriggerAI = useCallback((_ticketId: string) => {
    setRefreshTrigger((prev) => prev + 1)
    setActiveTab(2)
  }, [])

  // After triggering invoice from Tab 3 → switch to Tab 4
  const handleTriggerInvoice = useCallback((_ticketId: string) => {
    setRefreshTrigger((prev) => prev + 1)
    setActiveTab(3)
  }, [])

  const showTicketSelector = activeTab >= 1 && activeTab <= 3

  return (
    <div className="min-h-screen bg-mesh-gradient">
      <Header />
      <TabNav
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        selectedTicketId={selectedTicketId}
        onTicketSelect={setSelectedTicketId}
        showTicketSelector={showTicketSelector}
        refreshTrigger={refreshTrigger}
      />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div key={activeTab} className="tab-transition">
          {activeTab === 0 && (
            <TicketIngestion onTicketCreated={handleTicketCreated} />
          )}
          {activeTab === 1 && (
            <ExtractionResults
              ticketId={selectedTicketId}
              onTriggerAI={handleTriggerAI}
            />
          )}
          {activeTab === 2 && (
            <AIProcessingResults
              ticketId={selectedTicketId}
              onTriggerInvoice={handleTriggerInvoice}
            />
          )}
          {activeTab === 3 && (
            <InvoiceProcessing ticketId={selectedTicketId} />
          )}
          {activeTab === 4 && <Dashboard />}
        </div>
      </main>
    </div>
  )
}
