"""
Tests for the Ticket API endpoints (app.routers.tickets).

Uses FastAPI's TestClient with all Azure services mocked.
Covers:
  • POST /api/tickets — create with and without file
  • GET /api/tickets — list with pagination & filters
  • GET /api/tickets/{id} — get detail, 404
  • GET /api/tickets/{id}/extraction — Stage A result
  • GET /api/tickets/{id}/ai-processing — Stage B result
  • GET /api/tickets/{id}/invoice-processing — Stage C result
  • POST /api/tickets/{id}/process-ai — trigger Stage B
  • POST /api/tickets/{id}/process-invoice — trigger Stage C
  • POST /api/tickets/{id}/reprocess — re-trigger extraction
  • DELETE /api/tickets/{id} — delete, 404
"""

import io
import json
from unittest.mock import patch, MagicMock

import pytest

from app.models.ticket import TicketListResponse, TicketSummary, TicketStatus, Priority


# ═══════════════════════════════════════════════════════════════════
# POST /api/tickets
# ═══════════════════════════════════════════════════════════════════

class TestCreateTicket:
    def test_create_without_file(self, test_client):
        """Create a ticket with only form fields (no PDF)."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}

            resp = test_client.post(
                "/api/tickets",
                data={
                    "title": "Test Ticket",
                    "description": "Test description",
                    "tags": "invoice,test",
                    "priority": "normal",
                    "submitter": "user@test.com",
                    "submitter_name": "Test User",
                    "submitter_department": "QA",
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert "ticketId" in body
        assert body["status"] == "ingested"
        assert body["extractionQueued"] is False

    def test_create_with_pdf(self, test_client, sample_pdf_bytes):
        """Create a ticket with a PDF file — extraction should be queued."""
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob, \
             patch("app.routers.tickets.extraction") as mock_extract:
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}
            mock_blob.upload_pdf.return_value = {
                "blob_url": "https://test.blob.core.windows.net/inv.pdf",
                "size_bytes": len(sample_pdf_bytes),
            }

            resp = test_client.post(
                "/api/tickets",
                data={
                    "title": "Invoice Ticket",
                    "description": "With PDF",
                },
                files={"file": ("test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["extractionQueued"] is True
        assert body["attachment"] is not None

    def test_create_rejects_non_pdf(self, test_client):
        """Non-PDF files should be rejected with 400."""
        resp = test_client.post(
            "/api/tickets",
            data={"title": "Bad File", "description": "Not a PDF"},
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 400
        assert "Invalid file type" in resp.json()["detail"]

    def test_create_cosmos_failure(self, test_client):
        """If Cosmos DB create fails, return 500."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.create_ticket.side_effect = Exception("Cosmos unavailable")

            resp = test_client.post(
                "/api/tickets",
                data={"title": "Failing Ticket", "description": "Will fail"},
            )

        assert resp.status_code == 500
        assert "Failed to create ticket" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets
# ═══════════════════════════════════════════════════════════════════

class TestListTickets:
    def test_empty_list(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.list_tickets.return_value = TicketListResponse(
                tickets=[], total_count=0, page=1, page_size=20,
            )
            resp = test_client.get("/api/tickets")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 0
        assert body["tickets"] == []

    def test_paginated_list(self, test_client):
        summaries = [
            TicketSummary(
                ticket_id=f"ZAVA-{i}", title=f"Ticket {i}",
                status=TicketStatus.INGESTED, priority=Priority.NORMAL,
            )
            for i in range(3)
        ]
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.list_tickets.return_value = TicketListResponse(
                tickets=summaries, total_count=3, page=1, page_size=20,
            )
            resp = test_client.get("/api/tickets?page=1&page_size=20")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 3
        assert len(body["tickets"]) == 3

    def test_status_filter(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.list_tickets.return_value = TicketListResponse(
                tickets=[], total_count=0,
            )
            resp = test_client.get("/api/tickets?status=extracted")

        assert resp.status_code == 200
        mock_cosmos.list_tickets.assert_called_once_with(
            page=1, page_size=20, status_filter="extracted",
        )


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets/{ticket_id}
# ═══════════════════════════════════════════════════════════════════

class TestGetTicket:
    def test_found(self, test_client, sample_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = sample_ticket_doc
            resp = test_client.get("/api/tickets/ZAVA-2026-00001")

        assert resp.status_code == 200
        assert resp.json()["ticketId"] == "ZAVA-2026-00001"

    def test_not_found(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = None
            resp = test_client.get("/api/tickets/NONEXISTENT")

        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Stage-specific GET endpoints
# ═══════════════════════════════════════════════════════════════════

class TestStageEndpoints:
    def test_get_extraction_results(self, test_client, extracted_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = extracted_ticket_doc
            resp = test_client.get("/api/tickets/ZAVA-2026-00001/extraction")

        assert resp.status_code == 200
        body = resp.json()
        assert body["extraction"]["status"] == "completed"
        assert body["raw"]["title"]

    def test_get_ai_processing_results(self, test_client, ai_processed_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = ai_processed_ticket_doc
            resp = test_client.get("/api/tickets/ZAVA-2026-00001/ai-processing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["aiProcessing"]["status"] == "completed"

    def test_get_invoice_processing_results(self, test_client, sample_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = sample_ticket_doc
            resp = test_client.get("/api/tickets/ZAVA-2026-00001/invoice-processing")

        assert resp.status_code == 200
        body = resp.json()
        assert body["invoiceProcessing"]["status"] == "pending"

    def test_stage_endpoint_404(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = None
            resp = test_client.get("/api/tickets/NOPE/extraction")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# POST trigger endpoints
# ═══════════════════════════════════════════════════════════════════

class TestTriggerEndpoints:
    def test_trigger_ai_processing_ok(self, test_client, extracted_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.ai_processing"):
            mock_cosmos.get_ticket.return_value = extracted_ticket_doc
            resp = test_client.post("/api/tickets/ZAVA-2026-00001/process-ai")

        assert resp.status_code == 200
        body = resp.json()
        assert "queued" in body["message"].lower()

    def test_trigger_ai_processing_wrong_status(self, test_client, sample_ticket_doc):
        """Ticket in 'ingested' status can't trigger AI processing → 409."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = sample_ticket_doc
            resp = test_client.post("/api/tickets/ZAVA-2026-00001/process-ai")

        assert resp.status_code == 409

    def test_trigger_invoice_processing_ok(self, test_client, ai_processed_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.invoice_processing"):
            mock_cosmos.get_ticket.return_value = ai_processed_ticket_doc
            resp = test_client.post("/api/tickets/ZAVA-2026-00001/process-invoice")

        assert resp.status_code == 200

    def test_trigger_invoice_processing_wrong_status(self, test_client, extracted_ticket_doc):
        """Ticket in 'extracted' status can't trigger invoice → 409."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = extracted_ticket_doc
            resp = test_client.post("/api/tickets/ZAVA-2026-00001/process-invoice")

        assert resp.status_code == 409

    def test_trigger_not_found(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = None
            resp = test_client.post("/api/tickets/NOPE/process-ai")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# POST reprocess / DELETE
# ═══════════════════════════════════════════════════════════════════

class TestReprocessAndDelete:
    def test_reprocess_ok(self, test_client, extracted_ticket_doc):
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob, \
             patch("app.routers.tickets.extraction"):
            mock_cosmos.get_ticket.return_value = extracted_ticket_doc
            mock_cosmos.update_ticket.return_value = extracted_ticket_doc
            mock_blob.download_blob.return_value = b"fake-pdf"

            resp = test_client.post("/api/tickets/ZAVA-2026-00001/reprocess")

        assert resp.status_code == 200
        assert "reprocessing" in resp.json()["message"].lower()

    def test_reprocess_not_found(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = None
            resp = test_client.post("/api/tickets/NOPE/reprocess")
        assert resp.status_code == 404

    def test_delete_ok(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.delete_ticket.return_value = True
            resp = test_client.delete("/api/tickets/ZAVA-2026-00001")

        assert resp.status_code == 200
        assert resp.json()["message"] == "Ticket deleted."

    def test_delete_not_found(self, test_client):
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.delete_ticket.return_value = False
            resp = test_client.delete("/api/tickets/NOPE")

        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════

class TestHealthCheck:
    def test_health(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["service"] == "zava-ticket-processing-api"
        assert "dependencies" in body
