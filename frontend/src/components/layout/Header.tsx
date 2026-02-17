import { Zap } from 'lucide-react'

export default function Header() {
  return (
    <header className="bg-gradient-to-r from-indigo-950 via-indigo-900 to-indigo-800 header-gradient-animated">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-9 w-9 rounded-lg bg-indigo-600/40 ring-1 ring-indigo-400/30">
              <Zap className="h-5 w-5 text-indigo-200" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">
                ZAVA
                <span className="font-light ml-1.5 text-indigo-200">Processing Inc.</span>
              </h1>
            </div>
          </div>
          <div className="text-sm text-indigo-300 font-medium">
            AI-Powered Ticket Processing Pipeline
          </div>
        </div>
      </div>
    </header>
  )
}
