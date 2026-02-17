import { useState, useRef } from 'react'
import {
  Send,
  Upload,
  FileText,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FlaskConical,
  Zap,
  Brain,
} from 'lucide-react'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import { api } from '../../services/api'
import { SAMPLE_TICKETS, type SampleTicket } from '../../data/sampleTickets'
import type { Priority } from '../../types/ticket'

// ── API Base for fetching sample PDFs ─────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

interface TicketIngestionProps {
  onTicketCreated: (ticketId: string) => void
}

interface FeedItem {
  ticketId: string
  title: string
  priority: Priority
  timestamp: string
}

export default function TicketIngestion({ onTicketCreated }: TicketIngestionProps) {
  // ── Form state ──────────────────────────────────────
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [priority, setPriority] = useState<Priority>('normal')
  const [submitter, setSubmitter] = useState('')
  const [submitterName, setSubmitterName] = useState('')
  const [submitterDepartment, setSubmitterDepartment] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [extractionMethod, setExtractionMethod] = useState<'regex' | 'cu'>('regex')
  const [submitting, setSubmitting] = useState(false)
  const [loadingSample, setLoadingSample] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<{
    ticketId: string
    extractionQueued: boolean
  } | null>(null)

  // ── Feed state ──────────────────────────────────────
  const [feedItems, setFeedItems] = useState<FeedItem[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Helpers ─────────────────────────────────────────

  const loadSample = async (sample: SampleTicket) => {
    setTitle(sample.title)
    setDescription(sample.description)
    setTags(sample.tags)
    setPriority(sample.priority)
    setSubmitter(sample.submitter)
    setSubmitterName(sample.submitterName)
    setSubmitterDepartment(sample.submitterDepartment)
    setError(null)
    setSuccess(null)

    // Auto-fetch the matching sample PDF from the backend
    setLoadingSample(true)
    try {
      const pdfUrl = `${API_BASE}/data/${sample.pdfFilename}`
      const response = await fetch(pdfUrl)
      if (!response.ok) throw new Error(`Failed to fetch ${sample.pdfFilename}`)
      const blob = await response.blob()
      const fetchedFile = new File([blob], sample.pdfFilename, { type: 'application/pdf' })
      setFile(fetchedFile)
      // Update the file input display (reset native input since we set file programmatically)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch {
      // If fetch fails, clear the file and let the user upload manually
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } finally {
      setLoadingSample(false)
    }
  }

  const resetForm = () => {
    setTitle('')
    setDescription('')
    setTags('')
    setPriority('normal')
    setSubmitter('')
    setSubmitterName('')
    setSubmitterDepartment('')
    setFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      setError('Title is required.')
      return
    }

    setSubmitting(true)
    setError(null)
    setSuccess(null)

    try {
      const formData = new FormData()
      formData.append('title', title)
      formData.append('description', description)
      formData.append('tags', tags)
      formData.append('priority', priority)
      formData.append('submitter', submitter)
      formData.append('submitter_name', submitterName)
      formData.append('submitter_department', submitterDepartment)
      if (file) formData.append('file', file)
      formData.append('extraction_method', extractionMethod)

      const result = await api.createTicket(formData)

      setSuccess({
        ticketId: result.ticketId,
        extractionQueued: result.extractionQueued,
      })

      // Add to Salesforce feed
      setFeedItems((prev) => [
        {
          ticketId: result.ticketId,
          title,
          priority,
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ])

      resetForm()

      // Auto-navigate to extraction tab after a short delay
      setTimeout(() => onTicketCreated(result.ticketId), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit ticket')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Render ──────────────────────────────────────────

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* ── Left: Form ── */}
      <div className="lg:col-span-2 space-y-6">
        {/* Quick Demo Loader */}
        <Card
          title="Quick Demo — Load Sample Ticket"
          icon={<Sparkles className="h-4 w-4" />}
          accent="indigo"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {SAMPLE_TICKETS.map((sample, i) => (
              <button
                key={i}
                onClick={() => loadSample(sample)}
                disabled={loadingSample}
                className="text-left p-2.5 rounded-lg border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/50 transition-colors text-xs disabled:opacity-50 disabled:cursor-wait"
              >
                <span className="font-medium text-slate-700">
                  #{i + 1} {sample.scenario.replace(/_/g, ' ')}
                </span>
                <p className="text-slate-500 mt-0.5 truncate">{sample.scenarioLabel}</p>
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-400 mt-3">
            💡 Click a sample to auto-fill the form and attach the matching PDF
            {loadingSample && (
              <span className="ml-2 inline-flex items-center gap-1 text-indigo-500">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading PDF…
              </span>
            )}
          </p>
        </Card>

        {/* Submission Form */}
        <Card title="Submit New Ticket" icon={<Send className="h-4 w-4" />} accent="indigo">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Title */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Title *</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Invoice Processing Request - Vendor Name - Items"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow"
                required
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the ticket request…"
                rows={3}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow resize-none"
              />
            </div>

            {/* Priority + Tags */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Priority</label>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow"
                >
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Tags</label>
                <input
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="invoice, vendor-abc, urgent"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow"
                />
              </div>
            </div>

            {/* Submitter info */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Submitter Email
                </label>
                <input
                  type="text"
                  value={submitter}
                  onChange={(e) => setSubmitter(e.target.value)}
                  placeholder="user@company.com"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Submitter Name
                </label>
                <input
                  type="text"
                  value={submitterName}
                  onChange={(e) => setSubmitterName(e.target.value)}
                  placeholder="Jane Smith"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Department</label>
                <input
                  type="text"
                  value={submitterDepartment}
                  onChange={(e) => setSubmitterDepartment(e.target.value)}
                  placeholder="Procurement"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-4 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow"
                />
              </div>
            </div>

            {/* File Upload */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                PDF Attachment
              </label>
              <div className="group border-2 border-dashed border-slate-300 rounded-xl p-6 text-center hover:border-indigo-400 hover:bg-indigo-50/30 transition-all duration-200">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="hidden"
                  id="pdf-upload"
                />
                <label htmlFor="pdf-upload" className="cursor-pointer">
                  {file ? (
                    <div className="flex items-center justify-center gap-3 text-indigo-600">
                      <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-indigo-100">
                        <FileText className="h-5 w-5" />
                      </div>
                      <div className="text-left">
                        <span className="text-sm font-medium block">{file.name}</span>
                        <span className="text-xs text-slate-400">
                          {(file.size / 1024).toFixed(1)} KB
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2">
                      <div className="flex items-center justify-center h-12 w-12 rounded-full bg-slate-100 group-hover:bg-indigo-100 group-hover:scale-110 transition-all duration-200">
                        <Upload className="h-6 w-6 text-slate-400 group-hover:text-indigo-500 transition-colors" />
                      </div>
                      <span className="text-sm text-slate-600 font-medium">
                        Click to upload PDF invoice
                      </span>
                      <span className="text-xs text-slate-400">PDF files up to 50 MB</span>
                    </div>
                  )}
                </label>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            {/* Success */}
            {success && (
              <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <div>
                  Ticket{' '}
                  <span className="font-mono font-bold">{success.ticketId}</span>{' '}
                  created successfully!
                  {success.extractionQueued && ' Extraction started.'}
                  <span className="text-emerald-500 ml-1">
                    Switching to extraction view…
                  </span>
                </div>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={submitting || !title.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white font-medium text-sm rounded-lg hover:bg-indigo-700 hover:shadow-soft-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Submitting…
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Submit Ticket
                </>
              )}
            </button>
          </form>
        </Card>
      </div>

      {/* ── Right: Salesforce Feed Simulation ── */}
      <div className="space-y-4">
        <Card
          title="Salesforce Feed"
          subtitle="Simulated case arrival notifications"
          icon={
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
          }
        >
          {feedItems.length === 0 ? (
            <div className="text-center py-8">
              <FileText className="h-10 w-10 text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-400">No tickets submitted yet.</p>
              <p className="text-xs text-slate-400 mt-1">
                Submit a ticket to see it appear here.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {feedItems.map((item) => (
                <div
                  key={item.ticketId}
                  className="animate-slide-in p-3 bg-slate-50 rounded-lg border border-slate-100"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-xs text-slate-500">
                      {item.ticketId}
                    </span>
                    <Badge variant="priority" value={item.priority} />
                  </div>
                  <p className="text-sm text-slate-700 line-clamp-2">{item.title}</p>
                  <p className="text-xs text-slate-400 mt-1.5">
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* ── Extraction Method Toggle ── */}
        <Card
          title="Extraction Method"
          subtitle="Choose how PDFs are analyzed"
          icon={<FlaskConical className="h-4 w-4" />}
          accent="violet"
        >
          <div className="space-y-2">
            {/* Python Regex option */}
            <button
              type="button"
              onClick={() => setExtractionMethod('regex')}
              className={`w-full flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-150 text-left ${
                extractionMethod === 'regex'
                  ? 'border-indigo-300 bg-indigo-50/50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className={`flex items-center justify-center h-5 w-5 rounded-full border-2 shrink-0 ${
                extractionMethod === 'regex'
                  ? 'border-indigo-500'
                  : 'border-slate-300'
              }`}>
                {extractionMethod === 'regex' && (
                  <div className="h-2.5 w-2.5 rounded-full bg-indigo-500" />
                )}
              </div>
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <Zap className={`h-4 w-4 shrink-0 ${
                  extractionMethod === 'regex' ? 'text-indigo-600' : 'text-slate-400'
                }`} />
                <div className="min-w-0">
                  <div className={`text-sm font-medium ${
                    extractionMethod === 'regex' ? 'text-indigo-900' : 'text-slate-700'
                  }`}>Python Regex</div>
                  <div className="text-xs text-slate-500">Fast local parsing with pattern matching</div>
                </div>
              </div>
              <span className={`text-xs font-mono px-2 py-0.5 rounded-full shrink-0 ${
                extractionMethod === 'regex'
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'bg-slate-100 text-slate-500'
              }`}>~40ms</span>
            </button>

            {/* Content Understanding option */}
            <button
              type="button"
              onClick={() => setExtractionMethod('cu')}
              className={`w-full flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-150 text-left ${
                extractionMethod === 'cu'
                  ? 'border-indigo-300 bg-indigo-50/50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className={`flex items-center justify-center h-5 w-5 rounded-full border-2 shrink-0 ${
                extractionMethod === 'cu'
                  ? 'border-indigo-500'
                  : 'border-slate-300'
              }`}>
                {extractionMethod === 'cu' && (
                  <div className="h-2.5 w-2.5 rounded-full bg-indigo-500" />
                )}
              </div>
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <Brain className={`h-4 w-4 shrink-0 ${
                  extractionMethod === 'cu' ? 'text-indigo-600' : 'text-slate-400'
                }`} />
                <div className="min-w-0">
                  <div className={`text-sm font-medium ${
                    extractionMethod === 'cu' ? 'text-indigo-900' : 'text-slate-700'
                  }`}>Content Understanding</div>
                  <div className="text-xs text-slate-500">Azure AI document analysis</div>
                </div>
              </div>
              <span className={`text-xs font-mono px-2 py-0.5 rounded-full shrink-0 ${
                extractionMethod === 'cu'
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'bg-slate-100 text-slate-500'
              }`}>~30s</span>
            </button>
          </div>
        </Card>

        <div className="p-4 bg-indigo-50 border border-indigo-100 rounded-lg">
          <h4 className="text-sm font-medium text-indigo-900 mb-1">💡 Demo Tip</h4>
          <p className="text-xs text-indigo-700">
            Use the "Quick Demo" buttons above to load sample data with the
            matching PDF auto-attached. Just click a sample and hit Submit!
            You'll be automatically navigated to the extraction results.
          </p>
        </div>
      </div>
    </div>
  )
}
