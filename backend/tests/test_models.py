"""
Tests for Pydantic models (app.models.ticket).

Covers:
  • Enum values & membership
  • Model defaults, serialization, alias support
  • Field validation (types, optional fields)
  • TicketDocument camelCase aliases (populate_by_name)
  • DashboardMetrics, TicketListResponse
"""

import pytest
from datetime import datetime, timezone

from app.models.ticket import (
    TicketStatus,
    Priority,
    NextAction,
    AttachmentInfo,
    LineItem,
    ConfidenceScores,
    RawTicketData,
    BasicMetadata,
    ContentUnderstandingResult,
    ExtractionResult,
    StandardizedCodes,
    AIProcessingResult,
    InvoiceValidations,
    PaymentSubmission,
    InvoiceProcessingResult,
    TicketDocument,
    TicketCreateRequest,
    TicketSummary,
    TicketListResponse,
    DashboardMetrics,
)


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════

class TestTicketStatus:
    def test_all_values(self):
        expected = {
            "ingested", "extracting", "extracted",
            "ai_processing", "ai_processed",
            "invoice_processing", "invoice_processed",
            "error",
        }
        assert {s.value for s in TicketStatus} == expected

    def test_string_coercion(self):
        assert TicketStatus("ingested") is TicketStatus.INGESTED
        assert TicketStatus.ERROR.value == "error"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            TicketStatus("nonexistent")


class TestPriority:
    def test_values(self):
        assert {p.value for p in Priority} == {"normal", "high", "urgent"}


class TestNextAction:
    def test_values(self):
        expected = {"invoice_processing", "manual_review", "vendor_approval", "budget_approval"}
        assert {a.value for a in NextAction} == expected


# ═══════════════════════════════════════════════════════════════════
# Nested models
# ═══════════════════════════════════════════════════════════════════

class TestAttachmentInfo:
    def test_defaults(self):
        a = AttachmentInfo(filename="test.pdf")
        assert a.blob_url == ""
        assert a.content_type == "application/pdf"
        assert a.size_bytes == 0

    def test_full(self):
        a = AttachmentInfo(
            filename="inv.pdf", blob_url="https://example.com/inv.pdf",
            content_type="application/pdf", size_bytes=12345,
        )
        assert a.filename == "inv.pdf"
        assert a.size_bytes == 12345


class TestLineItem:
    def test_defaults(self):
        li = LineItem(description="Widget")
        assert li.product_code == ""
        assert li.quantity == 0
        assert li.amount == 0

    def test_full(self):
        li = LineItem(
            description="Valve", product_code="VLV-001",
            quantity=10, unit_price=100.50, amount=1005.00,
        )
        assert li.amount == 1005.00


class TestConfidenceScores:
    def test_all_zero_default(self):
        c = ConfidenceScores()
        assert c.overall == 0.0

    def test_values(self):
        c = ConfidenceScores(invoice_number=0.95, total_amount=0.88, vendor_name=0.90, overall=0.91)
        assert c.invoice_number == 0.95


class TestRawTicketData:
    def test_minimal(self):
        r = RawTicketData(title="Test", description="Desc")
        assert r.tags == []
        assert r.priority == Priority.NORMAL

    def test_full(self):
        r = RawTicketData(
            title="Invoice", description="Process this",
            tags=["invoice", "urgent"], priority=Priority.HIGH,
            submitter="user@test.com", submitter_name="User",
            submitter_department="Finance",
        )
        assert r.priority == Priority.HIGH
        assert len(r.tags) == 2


# ═══════════════════════════════════════════════════════════════════
# Stage result models
# ═══════════════════════════════════════════════════════════════════

class TestExtractionResult:
    def test_defaults(self):
        e = ExtractionResult()
        assert e.status == "pending"
        assert e.basic_metadata is None
        assert e.content_understanding is None

    def test_completed(self):
        e = ExtractionResult(
            status="completed",
            processing_time_ms=1500,
            basic_metadata=BasicMetadata(page_count=3, file_size_bytes=50000),
        )
        assert e.processing_time_ms == 1500
        assert e.basic_metadata.page_count == 3


class TestAIProcessingResult:
    def test_defaults(self):
        a = AIProcessingResult()
        assert a.status == "pending"
        assert a.summary == ""
        assert a.next_action is None

    def test_completed(self):
        codes = StandardizedCodes(
            vendor_code="VND-ABC",
            product_codes=["P1", "P2"],
            department_code="DEPT-001",
            cost_center="CC-001",
        )
        a = AIProcessingResult(
            status="completed",
            standardized_codes=codes,
            summary="Test summary",
            next_action=NextAction.INVOICE_PROCESSING,
            confidence=0.92,
        )
        assert a.next_action == NextAction.INVOICE_PROCESSING
        assert a.standardized_codes.vendor_code == "VND-ABC"


class TestInvoiceProcessingResult:
    def test_defaults(self):
        i = InvoiceProcessingResult()
        assert i.validations is None
        assert i.payment_submission is None
        assert i.errors == []

    def test_with_validations(self):
        v = InvoiceValidations(
            invoice_number_valid=True,
            amount_correct=True,
            due_date_valid=True,
            vendor_approved=True,
            budget_available=True,
        )
        i = InvoiceProcessingResult(status="completed", validations=v)
        assert i.validations.invoice_number_valid is True

    def test_validations_optional_fields(self):
        """All validation fields should be Optional[bool] = None."""
        v = InvoiceValidations()
        assert v.invoice_number_valid is None
        assert v.amount_correct is None


class TestPaymentSubmission:
    def test_defaults(self):
        p = PaymentSubmission()
        assert p.submitted is False
        assert p.payment_id == ""

    def test_submitted(self):
        p = PaymentSubmission(
            submitted=True,
            payment_id="PAY-001",
            payment_method="ACH",
            expected_payment_date="2026-02-28",
        )
        assert p.submitted is True
        assert p.payment_method == "ACH"


# ═══════════════════════════════════════════════════════════════════
# TicketDocument (aliases, populate_by_name)
# ═══════════════════════════════════════════════════════════════════

class TestTicketDocument:
    def test_create_with_aliases(self):
        """TicketDocument can be created using camelCase aliases."""
        doc = TicketDocument(
            ticketId="ZAVA-2026-00001",
            status=TicketStatus.INGESTED,
        )
        assert doc.ticket_id == "ZAVA-2026-00001"

    def test_create_with_field_names(self):
        """populate_by_name allows snake_case too."""
        doc = TicketDocument(ticket_id="ZAVA-2026-00002")
        assert doc.ticket_id == "ZAVA-2026-00002"

    def test_default_status(self):
        doc = TicketDocument(ticket_id="ZAVA-TEST")
        assert doc.status == TicketStatus.INGESTED

    def test_default_extraction(self):
        doc = TicketDocument(ticket_id="ZAVA-TEST")
        assert doc.extraction.status == "pending"

    def test_optional_raw(self):
        doc = TicketDocument(ticket_id="ZAVA-TEST")
        assert doc.raw is None

    def test_serialization_aliases(self):
        """Serialized output should use camelCase aliases when by_alias=True."""
        doc = TicketDocument(ticket_id="ZAVA-TEST")
        data = doc.model_dump(by_alias=True)
        assert "ticketId" in data
        assert "aiProcessing" in data
        assert "invoiceProcessing" in data


# ═══════════════════════════════════════════════════════════════════
# API response models
# ═══════════════════════════════════════════════════════════════════

class TestTicketCreateRequest:
    def test_minimal(self):
        r = TicketCreateRequest(title="Test", description="Desc")
        assert r.priority == Priority.NORMAL
        assert r.tags == []

    def test_full(self):
        r = TicketCreateRequest(
            title="Test", description="Desc",
            tags=["a", "b"], priority=Priority.URGENT,
            submitter="user@test.com",
        )
        assert r.priority == Priority.URGENT


class TestTicketSummary:
    def test_defaults(self):
        s = TicketSummary(
            ticket_id="ZAVA-001", title="Test",
            status=TicketStatus.INGESTED, priority=Priority.NORMAL,
        )
        assert s.has_extraction is False
        assert s.has_ai_processing is False

    def test_full(self):
        s = TicketSummary(
            ticket_id="ZAVA-001", title="Test",
            status=TicketStatus.INVOICE_PROCESSED,
            priority=Priority.HIGH,
            submitter_name="John",
            has_extraction=True,
            has_ai_processing=True,
            has_invoice_processing=True,
        )
        assert s.has_invoice_processing is True


class TestTicketListResponse:
    def test_empty(self):
        r = TicketListResponse(tickets=[], total_count=0)
        assert r.page == 1
        assert r.page_size == 20

    def test_with_tickets(self):
        t = TicketSummary(
            ticket_id="Z1", title="T", status=TicketStatus.INGESTED, priority=Priority.NORMAL,
        )
        r = TicketListResponse(tickets=[t], total_count=1, page=1, page_size=10)
        assert len(r.tickets) == 1


class TestDashboardMetrics:
    def test_defaults(self):
        m = DashboardMetrics()
        assert m.total_tickets == 0
        assert m.success_rate == 0.0
        assert m.tickets_by_status == {}

    def test_full(self):
        m = DashboardMetrics(
            total_tickets=100,
            tickets_by_status={"ingested": 10, "invoice_processed": 80, "error": 10},
            avg_extraction_time_ms=500.0,
            avg_ai_processing_time_ms=3000.0,
            avg_invoice_processing_time_ms=2000.0,
            avg_total_pipeline_time_ms=5500.0,
            success_rate=0.89,
            payment_submitted_count=75,
            manual_review_count=5,
            error_count=10,
        )
        assert m.success_rate == 0.89
        assert m.total_tickets == 100
