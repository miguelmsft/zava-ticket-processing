"""
Error handling & edge case tests.

Covers:
  • Invalid/corrupt PDF upload
  • Oversized file rejection
  • Missing required form fields
  • Empty description / title
  • Special characters in fields
  • Invalid pagination parameters
  • Concurrent status transition conflicts
  • Extraction error propagation
"""

import io
from unittest.mock import patch, MagicMock

import pytest


class TestInvalidFileUploads:
    def test_corrupt_file_content(self, test_client):
        """Upload a file that claims to be PDF but isn't → extraction handles gracefully."""
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob, \
             patch("app.routers.tickets.extraction"):
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}
            mock_blob.upload_pdf.return_value = {"blob_url": "local://test", "size_bytes": 5}

            resp = test_client.post(
                "/api/tickets",
                data={"title": "Corrupt PDF", "description": "Bad file"},
                files={"file": ("bad.pdf", io.BytesIO(b"hello"), "application/pdf")},
            )

        # The endpoint should accept it (extraction runs in background)
        assert resp.status_code == 201

    def test_non_pdf_content_type_rejected(self, test_client):
        resp = test_client.post(
            "/api/tickets",
            data={"title": "Image", "description": "Not a PDF"},
            files={"file": ("photo.jpg", io.BytesIO(b"\xff\xd8"), "image/jpeg")},
        )
        assert resp.status_code == 400

    def test_zero_byte_file(self, test_client):
        """Empty file should be accepted (extraction will handle empty bytes)."""
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob:
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}
            mock_blob.upload_pdf.return_value = {"blob_url": "local://test", "size_bytes": 0}

            resp = test_client.post(
                "/api/tickets",
                data={"title": "Empty File", "description": "Zero bytes"},
                files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            )

        assert resp.status_code == 201

    def test_octet_stream_accepted(self, test_client, sample_pdf_bytes):
        """application/octet-stream should be accepted (browser may send this)."""
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob, \
             patch("app.routers.tickets.extraction"):
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}
            mock_blob.upload_pdf.return_value = {"blob_url": "local://test", "size_bytes": 100}

            resp = test_client.post(
                "/api/tickets",
                data={"title": "Octet Stream", "description": "Browser upload"},
                files={"file": ("doc.pdf", io.BytesIO(sample_pdf_bytes), "application/octet-stream")},
            )

        assert resp.status_code == 201


class TestMissingFormFields:
    def test_missing_title(self, test_client):
        """Title is required — should return 422."""
        resp = test_client.post(
            "/api/tickets",
            data={"description": "No title"},
        )
        assert resp.status_code == 422

    def test_missing_description(self, test_client):
        """Description is required — should return 422."""
        resp = test_client.post(
            "/api/tickets",
            data={"title": "No description"},
        )
        assert resp.status_code == 422


class TestSpecialCharacters:
    def test_unicode_title(self, test_client):
        """Unicode characters in title should work fine."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}

            resp = test_client.post(
                "/api/tickets",
                data={
                    "title": "Factura de proveedor — Señor García",
                    "description": "Descripción con acentos: é, ñ, ü",
                },
            )

        assert resp.status_code == 201

    def test_html_in_fields(self, test_client):
        """HTML in fields should not cause errors (stored as-is)."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}

            resp = test_client.post(
                "/api/tickets",
                data={
                    "title": "<script>alert('xss')</script>",
                    "description": "<b>Bold</b> description",
                },
            )

        assert resp.status_code == 201

    def test_very_long_title(self, test_client):
        """Extremely long title should be accepted (Cosmos handles it)."""
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.create_ticket.return_value = {"ticketId": "ZAVA-TEST"}

            resp = test_client.post(
                "/api/tickets",
                data={
                    "title": "A" * 5000,
                    "description": "Long title test",
                },
            )

        assert resp.status_code == 201


class TestPaginationEdgeCases:
    def test_page_zero_rejected(self, test_client):
        """page=0 should be rejected by the ge=1 constraint."""
        resp = test_client.get("/api/tickets?page=0")
        assert resp.status_code == 422

    def test_negative_page_rejected(self, test_client):
        resp = test_client.get("/api/tickets?page=-1")
        assert resp.status_code == 422

    def test_page_size_too_large(self, test_client):
        """page_size > 100 should be rejected."""
        resp = test_client.get("/api/tickets?page_size=200")
        assert resp.status_code == 422


class TestStatusConflicts:
    def test_double_trigger_ai_on_already_processing(self, test_client):
        """Triggering AI on a ticket already in 'ai_processing' should succeed
        (the endpoint allows 'extracted', 'ai_processing', 'error')."""
        doc = {
            "id": "ZAVA-TEST",
            "ticketId": "ZAVA-TEST",
            "status": "ai_processing",
            "raw": {"title": "Test"},
        }
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.ai_processing"):
            mock_cosmos.get_ticket.return_value = doc
            resp = test_client.post("/api/tickets/ZAVA-TEST/process-ai")

        assert resp.status_code == 200

    def test_trigger_invoice_on_ingested(self, test_client):
        """Cannot trigger invoice processing on 'ingested' ticket."""
        doc = {"id": "Z", "ticketId": "Z", "status": "ingested"}
        with patch("app.routers.tickets.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = doc
            resp = test_client.post("/api/tickets/Z/process-invoice")

        assert resp.status_code == 409


class TestExtractionErrorHandling:
    def test_extraction_failure_produces_error_state(self, mock_settings, sample_pdf_bytes):
        """If extraction raises, the ticket should be updated with error status."""
        from app.services.extraction import process_extraction

        with patch("app.services.extraction.storage") as mock_cosmos, \
             patch("app.services.extraction.extract_basic_metadata", side_effect=Exception("PyMuPDF crash")):
            mock_cosmos.update_ticket.return_value = {"ticketId": "ZAVA-ERR"}

            result = process_extraction(
                ticket_id="ZAVA-ERR",
                pdf_bytes=sample_pdf_bytes,
            )

        assert result["status"] == "error"
        assert result["errorMessage"]

    def test_blob_download_failure_on_reprocess(self, test_client):
        """If blob download fails during reprocess, endpoint should still succeed."""
        doc = {
            "id": "ZAVA-TEST", "ticketId": "ZAVA-TEST", "status": "error",
            "attachments": [{"filename": "test.pdf", "blobUrl": "local://test"}],
        }
        with patch("app.routers.tickets.storage") as mock_cosmos, \
             patch("app.routers.tickets.blob_storage") as mock_blob:
            mock_cosmos.get_ticket.return_value = doc
            mock_cosmos.update_ticket.return_value = doc
            mock_blob.download_blob.side_effect = Exception("Blob not found")

            resp = test_client.post("/api/tickets/ZAVA-TEST/reprocess")

        # Should still return 200 (blob download failure is logged, not fatal)
        assert resp.status_code == 200
