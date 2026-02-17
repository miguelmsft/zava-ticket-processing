// ─── Enums & Literals ───────────────────────────────────────────

export type TicketStatus =
  | 'ingested'
  | 'extracting'
  | 'extracted'
  | 'ai_processing'
  | 'ai_processed'
  | 'invoice_processing'
  | 'invoice_processed'
  | 'error'

export type Priority = 'normal' | 'high' | 'urgent'

export type NextAction =
  | 'invoice_processing'
  | 'manual_review'
  | 'vendor_approval'
  | 'budget_approval'

// ─── Nested Models ──────────────────────────────────────────────

export interface AttachmentInfo {
  filename: string
  blobUrl: string
  contentType: string
  sizeBytes: number
}

export interface LineItem {
  description: string
  productCode: string
  quantity: number
  unitPrice: number
  amount: number
}

export interface ConfidenceScores {
  invoiceNumber: number
  totalAmount: number
  vendorName: number
  overall: number
}

export interface BasicMetadata {
  pageCount: number
  fileSizeBytes: number
  fileSizeDisplay: string
  pdfCreationDate: string | null
  rawTextPreview: string
}

export interface ContentUnderstandingResult {
  invoiceNumber: string
  vendorName: string
  vendorAddress: string
  invoiceDate: string | null
  dueDate: string | null
  poNumber: string
  subtotal: number
  taxAmount: number
  totalAmount: number
  currency: string
  paymentTerms: string
  lineItems: LineItem[]
  confidenceScores: ConfidenceScores | null
  hazardousFlag: boolean
  dotClassification: string
  billOfLading: string
  hazmatSurcharge: number
}

export interface ExtractionResult {
  status: string
  completedAt: string | null
  processingTimeMs: number
  extractionMethod?: string
  basicMetadata: BasicMetadata | null
  contentUnderstanding: ContentUnderstandingResult | null
  errorMessage: string | null
}

// ─── Stage B ────────────────────────────────────────────────────

export interface StandardizedCodes {
  vendorCode: string
  productCodes: string[]
  departmentCode: string
  costCenter: string
}

export interface AIProcessingResult {
  status: string
  completedAt: string | null
  processingTimeMs: number
  agentName: string
  agentVersion: string
  standardizedCodes: StandardizedCodes | null
  summary: string
  nextAction: NextAction | null
  flags: string[]
  confidence: number
  errorMessage: string | null
}

// ─── Stage C ────────────────────────────────────────────────────

export interface InvoiceValidations {
  invoiceNumberValid: boolean | null
  amountCorrect: boolean | null
  dueDateValid: boolean | null
  vendorApproved: boolean | null
  budgetAvailable: boolean | null
}

export interface PaymentSubmission {
  submitted: boolean
  paymentId: string
  submittedAt: string | null
  expectedPaymentDate: string | null
  paymentMethod: string
}

export interface InvoiceProcessingResult {
  status: string
  completedAt: string | null
  processingTimeMs: number
  agentName: string
  agentVersion: string
  validations: InvoiceValidations | null
  paymentSubmission: PaymentSubmission | null
  errors: string[]
  errorMessage: string | null
}

// ─── Raw Ticket Data ────────────────────────────────────────────

export interface RawTicketData {
  title: string
  description: string
  tags: string[]
  priority: Priority
  submitter: string
  submitterName: string
  submitterDepartment: string
}

// ─── Full Ticket Document (Cosmos DB) ───────────────────────────

export interface TicketDocument {
  id: string
  ticketId: string
  status: TicketStatus
  createdAt: string
  updatedAt: string
  raw: RawTicketData | null
  attachments: AttachmentInfo[]
  extraction: ExtractionResult
  aiProcessing: AIProcessingResult
  invoiceProcessing: InvoiceProcessingResult
}

// ─── API Response Models (snake_case from Pydantic) ─────────────

export interface TicketSummary {
  ticket_id: string
  title: string
  status: TicketStatus
  priority: Priority
  submitter_name: string
  created_at: string | null
  updated_at: string | null
  has_extraction: boolean
  has_ai_processing: boolean
  has_invoice_processing: boolean
}

export interface TicketListResponse {
  tickets: TicketSummary[]
  total_count: number
  page: number
  page_size: number
}

export interface DashboardMetrics {
  total_tickets: number
  tickets_by_status: Record<string, number>
  avg_extraction_time_ms: number
  avg_ai_processing_time_ms: number
  avg_invoice_processing_time_ms: number
  avg_total_pipeline_time_ms: number
  success_rate: number
  tickets_processed_today: number
  payment_submitted_count: number
  manual_review_count: number
  error_count: number
}

export interface TicketCreateResponse {
  ticketId: string
  status: string
  message: string
  attachment: AttachmentInfo | null
  extractionQueued: boolean
}
