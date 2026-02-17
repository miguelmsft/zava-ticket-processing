"""
Pydantic models for the Zava Processing ticket processing pipeline.

These models define the data contracts at every stage of the pipeline,
matching the Cosmos DB document schema in architecture/ARCHITECTURE.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════

class TicketStatus(str, Enum):
    """Pipeline status values for a ticket."""
    INGESTED = "ingested"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    AI_PROCESSING = "ai_processing"
    AI_PROCESSED = "ai_processed"
    INVOICE_PROCESSING = "invoice_processing"
    INVOICE_PROCESSED = "invoice_processed"
    ERROR = "error"


class Priority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NextAction(str, Enum):
    INVOICE_PROCESSING = "invoice_processing"
    MANUAL_REVIEW = "manual_review"
    VENDOR_APPROVAL = "vendor_approval"
    BUDGET_APPROVAL = "budget_approval"


# ═══════════════════════════════════════════════════════════════════
# Shared / Nested Models
# ═══════════════════════════════════════════════════════════════════

class AttachmentInfo(BaseModel):
    """Metadata about a ticket attachment (PDF invoice)."""
    filename: str
    blob_url: str = ""
    content_type: str = "application/pdf"
    size_bytes: int = 0


class LineItem(BaseModel):
    """A single line item extracted from an invoice."""
    description: str
    product_code: str = ""
    quantity: float = 0
    unit_price: float = 0
    amount: float = 0


class ConfidenceScores(BaseModel):
    """Confidence scores from Content Understanding extraction."""
    invoice_number: float = 0.0
    total_amount: float = 0.0
    vendor_name: float = 0.0
    overall: float = 0.0


# ═══════════════════════════════════════════════════════════════════
# Stage A: Ingestion & Extraction
# ═══════════════════════════════════════════════════════════════════

class RawTicketData(BaseModel):
    """Data captured directly from the ticket submission form."""
    title: str
    description: str
    tags: list[str] = []
    priority: Priority = Priority.NORMAL
    submitter: str = ""
    submitter_name: str = ""
    submitter_department: str = ""


class BasicMetadata(BaseModel):
    """Basic metadata extracted via Python libraries (PyMuPDF/pdfplumber)."""
    page_count: int = 0
    file_size_bytes: int = 0
    file_size_display: str = ""
    pdf_creation_date: Optional[str] = None
    raw_text_preview: str = ""


class ContentUnderstandingResult(BaseModel):
    """Structured data extracted via Azure Content Understanding."""
    invoice_number: str = ""
    vendor_name: str = ""
    vendor_address: str = ""
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: str = ""
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    currency: str = "USD"
    payment_terms: str = ""
    line_items: list[LineItem] = []
    confidence_scores: Optional[ConfidenceScores] = None
    # Optional fields for special invoice types
    hazardous_flag: bool = False
    dot_classification: str = ""
    bill_of_lading: str = ""
    hazmat_surcharge: float = 0.0


class ExtractionResult(BaseModel):
    """Combined extraction results (Stage A output)."""
    status: str = "pending"
    completed_at: Optional[datetime] = None
    processing_time_ms: int = 0
    basic_metadata: Optional[BasicMetadata] = None
    content_understanding: Optional[ContentUnderstandingResult] = None
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# Stage B: AI Information Processing
# ═══════════════════════════════════════════════════════════════════

class StandardizedCodes(BaseModel):
    """Codes standardized by the AI Information Processing agent."""
    vendor_code: str = ""
    product_codes: list[str] = []
    department_code: str = ""
    cost_center: str = ""


class AIProcessingResult(BaseModel):
    """AI Information Processing results (Stage B output)."""
    status: str = "pending"
    completed_at: Optional[datetime] = None
    processing_time_ms: int = 0
    agent_name: str = ""
    agent_version: str = ""
    standardized_codes: Optional[StandardizedCodes] = None
    summary: str = ""
    next_action: Optional[NextAction] = None
    flags: list[str] = []
    confidence: float = 0.0
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# Stage C: Invoice Processing
# ═══════════════════════════════════════════════════════════════════

class InvoiceValidations(BaseModel):
    """Individual validation checks performed by the Invoice Processing agent."""
    invoice_number_valid: Optional[bool] = None
    amount_correct: Optional[bool] = None
    due_date_valid: Optional[bool] = None
    vendor_approved: Optional[bool] = None
    budget_available: Optional[bool] = None


class PaymentSubmission(BaseModel):
    """Payment submission details (from simulated Payment API)."""
    submitted: bool = False
    payment_id: str = ""
    submitted_at: Optional[datetime] = None
    expected_payment_date: Optional[str] = None
    payment_method: str = ""


class InvoiceProcessingResult(BaseModel):
    """Invoice Processing results (Stage C output)."""
    status: str = "pending"
    completed_at: Optional[datetime] = None
    processing_time_ms: int = 0
    agent_name: str = ""
    agent_version: str = ""
    validations: Optional[InvoiceValidations] = None
    payment_submission: Optional[PaymentSubmission] = None
    errors: list[str] = []
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# Full Ticket Document (Cosmos DB)
# ═══════════════════════════════════════════════════════════════════

class TicketDocument(BaseModel):
    """
    Complete ticket document matching the Cosmos DB schema.

    This is the single source of truth for a ticket's state across
    all pipeline stages. Partition key: /ticketId.
    """
    id: str = ""
    ticket_id: str = Field(..., alias="ticketId")
    status: TicketStatus = TicketStatus.INGESTED
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        alias="updatedAt",
    )

    # Ingestion data
    raw: Optional[RawTicketData] = None
    attachments: list[AttachmentInfo] = []

    # Stage A
    extraction: ExtractionResult = Field(default_factory=ExtractionResult)

    # Stage B
    ai_processing: AIProcessingResult = Field(
        default_factory=AIProcessingResult,
        alias="aiProcessing",
    )

    # Stage C
    invoice_processing: InvoiceProcessingResult = Field(
        default_factory=InvoiceProcessingResult,
        alias="invoiceProcessing",
    )

    model_config = {
        "populate_by_name": True,
        "json_encoders": {datetime: lambda v: v.isoformat() + "Z" if v else None},
    }


# ═══════════════════════════════════════════════════════════════════
# API Request / Response Models
# ═══════════════════════════════════════════════════════════════════

class TicketCreateRequest(BaseModel):
    """Request body for creating a new ticket (form fields — file uploaded separately)."""
    title: str
    description: str
    tags: list[str] = []
    priority: Priority = Priority.NORMAL
    submitter: str = ""
    submitter_name: str = ""
    submitter_department: str = ""


class TicketSummary(BaseModel):
    """Lightweight ticket summary for list views."""
    ticket_id: str
    title: str
    status: TicketStatus
    priority: Priority
    submitter_name: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    has_extraction: bool = False
    has_ai_processing: bool = False
    has_invoice_processing: bool = False


class TicketListResponse(BaseModel):
    """Paginated list of tickets."""
    tickets: list[TicketSummary]
    total_count: int
    page: int = 1
    page_size: int = 20


class DashboardMetrics(BaseModel):
    """Aggregated metrics for the dashboard (Tab 5)."""
    total_tickets: int = 0
    tickets_by_status: dict[str, int] = {}
    avg_extraction_time_ms: float = 0.0
    avg_ai_processing_time_ms: float = 0.0
    avg_invoice_processing_time_ms: float = 0.0
    avg_total_pipeline_time_ms: float = 0.0
    success_rate: float = 0.0
    tickets_processed_today: int = 0
    payment_submitted_count: int = 0
    manual_review_count: int = 0
    error_count: int = 0
