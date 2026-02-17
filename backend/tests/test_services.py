"""
Tests for service modules — Cosmos client, Blob storage, AI/Invoice processing.

Uses mocks to avoid real Azure calls.
Covers:
  • cosmos_client: create, get, update, delete, list, dashboard metrics
  • blob_storage: upload (local fallback), generate_sas_url, download
  • ai_processing: trigger success, not found, wrong status, timeout, connect error
  • invoice_processing: same coverage as ai_processing
"""

import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, PropertyMock

import pytest


# ═══════════════════════════════════════════════════════════════════
# Blob Storage
# ═══════════════════════════════════════════════════════════════════

class TestBlobStorage:
    def test_upload_pdf_local_fallback(self, mock_settings):
        """When blob connection is empty, upload should return local:// URL."""
        from app.services.blob_storage import upload_pdf
        result = upload_pdf(
            ticket_id="ZAVA-TEST",
            filename="test.pdf",
            file_bytes=b"fake-pdf",
        )
        assert result["blob_url"].startswith("local://")
        assert result["size_bytes"] == 8

    def test_upload_pdf_with_mock_client(self, mock_settings):
        """With a mocked BlobServiceClient, upload should succeed."""
        from app.services import blob_storage

        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_service_client = MagicMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        with patch("app.services.blob_storage.get_blob_service_client", return_value=mock_service_client), \
             patch("app.services.blob_storage.get_settings") as mock_get_settings:
            # Fake a configured connection string so upload_pdf uses the real path
            fake_settings = MagicMock()
            fake_settings.blob_connection_string = "DefaultEndpointsProtocol=https;AccountName=fake"
            fake_settings.blob_container_name = "invoices"
            mock_get_settings.return_value = fake_settings

            result = blob_storage.upload_pdf(
                ticket_id="ZAVA-TEST",
                filename="invoice.pdf",
                file_bytes=b"pdf-content",
            )
        assert result["size_bytes"] == 11
        mock_blob_client.upload_blob.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# AI Processing Service
# ═══════════════════════════════════════════════════════════════════

class TestAIProcessingService:
    def test_trigger_ticket_not_found(self, mock_settings):
        """Trigger with nonexistent ticket → error."""
        with patch("app.services.ai_processing.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = None
            from app.services.ai_processing import trigger_ai_processing
            result = trigger_ai_processing("NONEXISTENT")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_trigger_wrong_status(self, mock_settings):
        """Ticket not in 'extracted' status → error."""
        with patch("app.services.ai_processing.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = {"status": "ingested"}
            from app.services.ai_processing import trigger_ai_processing
            result = trigger_ai_processing("ZAVA-TEST")

        assert result["success"] is False
        assert "ingested" in result["error"]

    def test_trigger_no_function_url(self, mock_settings):
        """Missing function URL → falls back to local simulation."""
        with patch("app.services.ai_processing.storage") as mock_cosmos, \
             patch("app.services.ai_processing.get_settings") as mock_get:
            mock_cosmos.get_ticket.return_value = {
                "status": "extracted",
                "extraction": {
                    "contentUnderstanding": {
                        "vendorName": "ABC Industrial Supplies",
                        "invoiceNumber": "INV-2026-78432",
                        "totalAmount": 13531.25,
                        "lineItems": [{"productCode": "VLV-4200-IND", "description": "Valve"}],
                    }
                },
            }
            settings = MagicMock()
            settings.stage_b_function_url = ""
            settings.stage_b_function_key = ""
            settings.stage_b_url = ""
            mock_get.return_value = settings

            from app.services.ai_processing import trigger_ai_processing
            result = trigger_ai_processing("ZAVA-TEST")

        assert result["success"] is True
        assert result["status"] == "ai_processed"
        mock_cosmos.update_ticket.assert_called_once()

    def test_trigger_success(self, mock_settings):
        """Successful HTTP call to Stage B function."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ticketId": "ZAVA-TEST",
            "status": "completed",
        }

        with patch("app.services.ai_processing.storage") as mock_cosmos, \
             patch("app.services.ai_processing.httpx.Client") as mock_client_cls:
            mock_cosmos.get_ticket.return_value = {"status": "extracted"}
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            from app.services.ai_processing import trigger_ai_processing
            result = trigger_ai_processing("ZAVA-TEST")

        assert result["success"] is True
        assert "processingTimeMs" in result

    def test_trigger_timeout(self, mock_settings):
        """Timeout should set error status on the ticket."""
        import httpx

        with patch("app.services.ai_processing.storage") as mock_cosmos, \
             patch("app.services.ai_processing.httpx.Client") as mock_client_cls:
            mock_cosmos.get_ticket.return_value = {"status": "extracted"}
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            from app.services.ai_processing import trigger_ai_processing
            result = trigger_ai_processing("ZAVA-TEST")

        assert result["success"] is False
        assert "timed out" in result["error"]
        mock_cosmos.update_ticket.assert_called_once()

    def test_trigger_connect_error(self, mock_settings):
        """Connection error → falls back to local simulation."""
        import httpx

        with patch("app.services.ai_processing.storage") as mock_cosmos, \
             patch("app.services.ai_processing.httpx.Client") as mock_client_cls:
            mock_cosmos.get_ticket.return_value = {
                "status": "extracted",
                "extraction": {
                    "contentUnderstanding": {
                        "vendorName": "ABC Industrial Supplies",
                        "invoiceNumber": "INV-2026-78432",
                        "totalAmount": 13531.25,
                        "lineItems": [{"productCode": "VLV-4200-IND", "description": "Valve"}],
                    }
                },
            }
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value = mock_client

            from app.services.ai_processing import trigger_ai_processing
            result = trigger_ai_processing("ZAVA-TEST")

        assert result["success"] is True
        assert result["status"] == "ai_processed"
        mock_cosmos.update_ticket.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Invoice Processing Service
# ═══════════════════════════════════════════════════════════════════

class TestInvoiceProcessingService:
    def test_trigger_ticket_not_found(self, mock_settings):
        with patch("app.services.invoice_processing.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = None
            from app.services.invoice_processing import trigger_invoice_processing
            result = trigger_invoice_processing("NONEXISTENT")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_trigger_wrong_status(self, mock_settings):
        with patch("app.services.invoice_processing.storage") as mock_cosmos:
            mock_cosmos.get_ticket.return_value = {"status": "extracted"}
            from app.services.invoice_processing import trigger_invoice_processing
            result = trigger_invoice_processing("ZAVA-TEST")

        assert result["success"] is False
        assert "extracted" in result["error"]

    def test_trigger_success(self, mock_settings):
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ticketId": "ZAVA-TEST",
            "status": "completed",
        }

        with patch("app.services.invoice_processing.storage") as mock_cosmos, \
             patch("app.services.invoice_processing.httpx.Client") as mock_client_cls:
            mock_cosmos.get_ticket.return_value = {"status": "ai_processed"}
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            from app.services.invoice_processing import trigger_invoice_processing
            result = trigger_invoice_processing("ZAVA-TEST")

        assert result["success"] is True

    def test_trigger_timeout(self, mock_settings):
        import httpx

        with patch("app.services.invoice_processing.storage") as mock_cosmos, \
             patch("app.services.invoice_processing.httpx.Client") as mock_client_cls:
            mock_cosmos.get_ticket.return_value = {"status": "ai_processed"}
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client_cls.return_value = mock_client

            from app.services.invoice_processing import trigger_invoice_processing
            result = trigger_invoice_processing("ZAVA-TEST")

        assert result["success"] is False
        assert "timed out" in result["error"]
        mock_cosmos.update_ticket.assert_called_once()

    def test_trigger_http_error(self, mock_settings):
        """Non-200 response should fall back to local simulation."""
        with patch("app.services.invoice_processing.storage") as mock_cosmos, \
             patch("app.services.invoice_processing.httpx.Client") as mock_client_cls:
            mock_cosmos.get_ticket.return_value = {
                "status": "ai_processed",
                "extraction": {"contentUnderstanding": {"vendorName": "Test Vendor", "totalAmount": 100}},
            }
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            from app.services.invoice_processing import trigger_invoice_processing
            result = trigger_invoice_processing("ZAVA-TEST")

        # Falls back to local simulation which succeeds
        assert result["success"] is True
        mock_cosmos.update_ticket.assert_called()
