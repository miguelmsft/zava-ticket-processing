"""
Integration test: Full pipeline simulation (ingest → extract → AI → invoice → dashboard).

This test simulates the entire ticket lifecycle using mocked Azure services
to verify the data flows correctly through all stages without needing
live cloud resources.

Covers:
  • Ticket creation with PDF upload
  • Stage A extraction runs and updates the ticket
  • Stage B AI processing trigger and result verification
  • Stage C Invoice processing trigger and result verification
  • Dashboard metrics reflect the processed ticket
"""

import io
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

import pytest

from app.models.ticket import (
    TicketStatus,
    TicketListResponse,
    TicketSummary,
    Priority,
    DashboardMetrics,
)


class TestFullPipelineIntegration:
    """Simulate the entire ticket lifecycle through the API."""

    def test_happy_path_pipeline(self, test_client, sample_pdf_bytes):
        """
        Full happy-path:
          1. POST /api/tickets (create with PDF)
          2. GET /api/tickets/{id}/extraction (verify extraction queued)
          3. POST /api/tickets/{id}/process-ai (trigger Stage B)
          4. GET /api/tickets/{id}/ai-processing (verify AI result)
          5. POST /api/tickets/{id}/process-invoice (trigger Stage C)
          6. GET /api/tickets/{id}/invoice-processing (verify invoice result)
          7. GET /api/dashboard/metrics (verify metrics updated)
        """
        ticket_id = "ZAVA-2026-99999"
        now = datetime.now(timezone.utc).isoformat()

        # ── Step 1: Create ticket ────────────────────────────
        ingested_doc = _make_doc(ticket_id, "ingested", now)
        extracted_doc = _make_doc(ticket_id, "extracted", now, extraction_done=True)
        ai_processed_doc = _make_doc(ticket_id, "ai_processed", now, extraction_done=True, ai_done=True)
        invoice_processed_doc = _make_doc(
            ticket_id, "invoice_processed", now,
            extraction_done=True, ai_done=True, invoice_done=True,
        )

        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob, \
             patch("app.routers.tickets.extraction") as mock_extract:
            mock_cosmos.create_ticket.return_value = ingested_doc
            mock_blob.upload_pdf.return_value = {"blob_url": "local://test", "size_bytes": 100}

            resp = test_client.post(
                "/api/tickets",
                data={"title": "Integration Test", "description": "Full pipeline test"},
                files={"file": ("test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["extractionQueued"] is True

        # ── Step 2: Verify extraction result ────────────────
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = extracted_doc
            resp = test_client.get(f"/api/tickets/{ticket_id}/extraction")

        assert resp.status_code == 200
        assert resp.json()["extraction"]["status"] == "completed"

        # ── Step 3: Trigger AI processing ────────────────────
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.ai_processing"):
            mock_cosmos.get_ticket.return_value = extracted_doc
            resp = test_client.post(f"/api/tickets/{ticket_id}/process-ai")

        assert resp.status_code == 200

        # ── Step 4: Verify AI result ─────────────────────────
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = ai_processed_doc
            resp = test_client.get(f"/api/tickets/{ticket_id}/ai-processing")

        assert resp.status_code == 200
        ai_result = resp.json()["aiProcessing"]
        assert ai_result["status"] == "completed"
        assert ai_result["nextAction"] == "invoice_processing"

        # ── Step 5: Trigger Invoice processing ───────────────
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.invoice_processing"):
            mock_cosmos.get_ticket.return_value = ai_processed_doc
            resp = test_client.post(f"/api/tickets/{ticket_id}/process-invoice")

        assert resp.status_code == 200

        # ── Step 6: Verify Invoice result ────────────────────
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = invoice_processed_doc
            resp = test_client.get(f"/api/tickets/{ticket_id}/invoice-processing")

        assert resp.status_code == 200
        inv = resp.json()["invoiceProcessing"]
        assert inv["status"] == "completed"
        assert inv["paymentSubmission"]["submitted"] is True

        # ── Step 7: Dashboard metrics ────────────────────────
        mock_metrics = DashboardMetrics(
            total_tickets=1,
            tickets_by_status={"invoice_processed": 1},
            avg_extraction_time_ms=800.0,
            avg_ai_processing_time_ms=3000.0,
            avg_invoice_processing_time_ms=2000.0,
            avg_total_pipeline_time_ms=5800.0,
            success_rate=1.0,
            payment_submitted_count=1,
            manual_review_count=0,
            error_count=0,
        )
        with patch("app.routers.dashboard.storage") as mock_cosmos:
            mock_cosmos.compute_dashboard_metrics.return_value = mock_metrics
            resp = test_client.get("/api/dashboard/metrics")

        assert resp.status_code == 200
        metrics = resp.json()
        assert metrics["total_tickets"] == 1
        assert metrics["success_rate"] == 1.0
        assert metrics["payment_submitted_count"] == 1

    def test_error_recovery_pipeline(self, test_client, sample_pdf_bytes):
        """
        Error scenario: Extraction succeeds but AI fails → reprocess → success.
        """
        ticket_id = "ZAVA-2026-ERR01"
        now = datetime.now(timezone.utc).isoformat()

        error_doc = _make_doc(ticket_id, "error", now, extraction_done=True)
        error_doc["aiProcessing"]["status"] = "error"
        error_doc["aiProcessing"]["errorMessage"] = "Agent timed out"

        # AI processing returns 409 (wrong status after error)
        # But the reprocess endpoint should reset it back to ingested
        reprocessed_doc = _make_doc(ticket_id, "ingested", now)

        # ── Step 1: Reprocess the errored ticket ─────────────
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob, \
             patch("app.routers.tickets.extraction"):
            mock_cosmos.get_ticket.return_value = error_doc
            mock_cosmos.update_ticket.return_value = reprocessed_doc
            mock_blob.download_blob.return_value = sample_pdf_bytes

            resp = test_client.post(f"/api/tickets/{ticket_id}/reprocess")

        assert resp.status_code == 200
        assert "reprocessing" in resp.json()["message"].lower()

    def test_ticket_list_after_processing(self, test_client):
        """List endpoint should return all processed tickets."""
        summaries = [
            TicketSummary(
                ticket_id="Z1", title="Ticket 1",
                status=TicketStatus.INVOICE_PROCESSED, priority=Priority.NORMAL,
                has_extraction=True, has_ai_processing=True, has_invoice_processing=True,
            ),
            TicketSummary(
                ticket_id="Z2", title="Ticket 2",
                status=TicketStatus.ERROR, priority=Priority.HIGH,
                has_extraction=True, has_ai_processing=False,
            ),
        ]
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.list_tickets.return_value = TicketListResponse(
                tickets=summaries, total_count=2, page=1, page_size=20,
            )
            resp = test_client.get("/api/tickets")

        assert resp.status_code == 200
        tickets = resp.json()["tickets"]
        assert len(tickets) == 2
        statuses = {t["status"] for t in tickets}
        assert "invoice_processed" in statuses
        assert "error" in statuses


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_doc(
    ticket_id: str,
    status: str,
    now: str,
    extraction_done: bool = False,
    ai_done: bool = False,
    invoice_done: bool = False,
) -> dict:
    """Build a mock Cosmos DB ticket document at a given pipeline stage."""
    doc = {
        "id": ticket_id,
        "ticketId": ticket_id,
        "status": status,
        "createdAt": now,
        "updatedAt": now,
        "raw": {
            "title": f"Test - {ticket_id}",
            "description": "Integration test ticket",
            "tags": ["test"],
            "priority": "normal",
            "submitter": "test@zava.com",
            "submitterName": "Test User",
            "submitterDepartment": "QA",
        },
        "attachments": [
            {
                "filename": "test.pdf",
                "blobUrl": f"local://{ticket_id}/test.pdf",
                "contentType": "application/pdf",
                "sizeBytes": 100,
            }
        ],
        "extraction": {
            "status": "completed" if extraction_done else "pending",
            "completedAt": now if extraction_done else None,
            "processingTimeMs": 800 if extraction_done else 0,
            "basicMetadata": {
                "pageCount": 2,
                "fileSizeBytes": 45000,
                "fileSizeDisplay": "43.9 KB",
                "pdfCreationDate": now,
                "rawTextPreview": "Test invoice content",
            } if extraction_done else None,
            "contentUnderstanding": {
                "invoiceNumber": "INV-TEST-001",
                "vendorName": "Test Vendor",
                "vendorAddress": "123 Test St",
                "invoiceDate": "2026-01-22",
                "dueDate": "2026-02-21",
                "poNumber": "PO-TEST",
                "subtotal": 1000.00,
                "taxAmount": 82.50,
                "totalAmount": 1082.50,
                "currency": "USD",
                "paymentTerms": "NET-30",
                "lineItems": [],
                "confidenceScores": {
                    "invoiceNumber": 0.93,
                    "totalAmount": 0.96,
                    "vendorName": 0.91,
                    "overall": 0.93,
                },
                "hazardousFlag": False,
                "dotClassification": "",
                "billOfLading": "",
                "hazmatSurcharge": 0.0,
            } if extraction_done else None,
        },
        "aiProcessing": {
            "status": "completed" if ai_done else "pending",
            "completedAt": now if ai_done else None,
            "processingTimeMs": 3200 if ai_done else 0,
            "agentName": "Information Processing Agent" if ai_done else "",
            "agentVersion": "1.0" if ai_done else "",
            "standardizedCodes": {
                "vendorCode": "VND-TEST",
                "productCodes": ["P-001"],
                "departmentCode": "DEPT-QA",
                "costCenter": "CC-TEST",
            } if ai_done else None,
            "summary": "Test invoice summary" if ai_done else "",
            "nextAction": "invoice_processing" if ai_done else None,
            "flags": [],
            "confidence": 0.92 if ai_done else 0.0,
        },
        "invoiceProcessing": {
            "status": "completed" if invoice_done else "pending",
            "completedAt": now if invoice_done else None,
            "processingTimeMs": 2000 if invoice_done else 0,
            "agentName": "Invoice Processing Agent" if invoice_done else "",
            "agentVersion": "1.0" if invoice_done else "",
            "validations": {
                "invoiceNumberValid": True,
                "amountCorrect": True,
                "dueDateValid": True,
                "vendorApproved": True,
                "budgetAvailable": True,
            } if invoice_done else None,
            "paymentSubmission": {
                "submitted": True,
                "paymentId": "PAY-TEST-001",
                "submittedAt": now,
                "expectedPaymentDate": "2026-02-28",
                "paymentMethod": "ACH",
            } if invoice_done else None,
            "errors": [],
        },
    }
    return doc
