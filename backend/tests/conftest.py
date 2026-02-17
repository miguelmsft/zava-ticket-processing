"""
Shared fixtures for backend tests.

Provides:
  • mock_settings – patched Settings with dummy values (no real Azure calls)
  • mock_cosmos_container – a MagicMock that stands in for a Cosmos DB container
  • test_client – FastAPI TestClient with cosmos / blob fully mocked
  • sample_ticket_doc – a realistic in-memory ticket document
  • sample_pdf_bytes – real PDF bytes from the first sample invoice
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Ensure backend package is importable ──────────────────────────
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ── Root of the repo (for sample PDFs, etc.) ─────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_PDFS_DIR = REPO_ROOT / "data" / "sample_pdfs"


# ═══════════════════════════════════════════════════════════════════
# Environment — set dummy env vars BEFORE importing app modules
# ═══════════════════════════════════════════════════════════════════

_DUMMY_ENV = {
    "APP_ENV": "test",
    "LOG_LEVEL": "WARNING",
    "CORS_ORIGINS": "http://localhost:5173",
    "COSMOS_ENDPOINT": "https://localhost:8081",
    "COSMOS_KEY": "dGVzdGtleQ==",
    "COSMOS_DATABASE": "zava-test",
    "BLOB_CONNECTION_STRING": "",
    "CONTENT_UNDERSTANDING_ENDPOINT": "",
    "CONTENT_UNDERSTANDING_KEY": "",
    "AI_PROJECT_ENDPOINT": "",
    "STAGE_B_FUNCTION_URL": "http://localhost:7074/api/process-ticket",
    "STAGE_C_FUNCTION_URL": "http://localhost:7075/api/process-invoice",
}

# Force test environment — use direct assignment (not setdefault) so that
# pre-existing env vars from manual server runs (e.g. APP_ENV=development)
# don't leak into the test suite and cause spurious failures.
# See PLAN.md > Known Issues > "Backend Test Failures When APP_ENV=development Leaks"
for k, v in _DUMMY_ENV.items():
    os.environ[k] = v


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture()
def mock_settings():
    """Return a Settings instance that points at no real Azure services."""
    # Clear the lru_cache so our env vars are picked up
    from app.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture()
def mock_cosmos_container():
    """A MagicMock standing in for azure.cosmos.ContainerProxy."""
    container = MagicMock()
    container.create_item.return_value = {}
    container.upsert_item.side_effect = lambda body: body
    container.read_item.return_value = {}
    container.delete_item.return_value = None
    container.query_items.return_value = iter([])
    return container


@pytest.fixture()
def sample_ticket_doc():
    """A realistic Cosmos DB ticket document dictionary."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": "ZAVA-2026-00001",
        "ticketId": "ZAVA-2026-00001",
        "status": "ingested",
        "createdAt": now,
        "updatedAt": now,
        "raw": {
            "title": "Invoice Processing Request - ABC Industrial Supplies",
            "description": "Please process the attached invoice from ABC Industrial Supplies.",
            "tags": ["invoice", "vendor-abc"],
            "priority": "normal",
            "submitter": "john.doe@zavaprocessing.com",
            "submitterName": "John Doe",
            "submitterDepartment": "Procurement",
        },
        "attachments": [
            {
                "filename": "INV_ABC_Industrial_2026_78432.pdf",
                "blobUrl": "local://ZAVA-2026-00001/INV_ABC_Industrial_2026_78432.pdf",
                "contentType": "application/pdf",
                "sizeBytes": 45000,
            }
        ],
        "extraction": {
            "status": "pending",
            "completedAt": None,
            "basicMetadata": None,
            "contentUnderstanding": None,
        },
        "aiProcessing": {
            "status": "pending",
            "completedAt": None,
            "standardizedCodes": None,
            "summary": None,
            "nextAction": None,
        },
        "invoiceProcessing": {
            "status": "pending",
            "completedAt": None,
            "validations": None,
            "paymentSubmission": None,
            "errors": [],
        },
    }


@pytest.fixture()
def extracted_ticket_doc(sample_ticket_doc):
    """A ticket that has completed Stage A extraction."""
    doc = dict(sample_ticket_doc)
    doc["status"] = "extracted"
    doc["extraction"] = {
        "status": "completed",
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "processingTimeMs": 1250,
        "basicMetadata": {
            "pageCount": 2,
            "fileSizeBytes": 45000,
            "fileSizeDisplay": "43.9 KB",
            "pdfCreationDate": "2026-01-22T10:30:00+00:00",
            "rawTextPreview": "ABC Industrial Supplies\nINVOICE...",
        },
        "contentUnderstanding": {
            "invoiceNumber": "INV-2026-78432",
            "vendorName": "ABC Industrial Supplies",
            "vendorAddress": "123 Industrial Way, Houston, TX 77001",
            "invoiceDate": "2026-01-22",
            "dueDate": "2026-02-21",
            "poNumber": "PO-2026-1150",
            "subtotal": 12500.00,
            "taxAmount": 1031.25,
            "totalAmount": 13531.25,
            "currency": "USD",
            "paymentTerms": "NET-30",
            "lineItems": [
                {
                    "description": "Industrial Grade Valve Assembly (Model V-4200)",
                    "productCode": "VLV-4200-IND",
                    "quantity": 50,
                    "unitPrice": 150.00,
                    "amount": 7500.00,
                },
            ],
            "confidenceScores": {
                "invoiceNumber": 0.93,
                "totalAmount": 0.96,
                "vendorName": 0.91,
                "overall": 0.9333,
            },
            "hazardousFlag": False,
            "dotClassification": "",
            "billOfLading": "",
            "hazmatSurcharge": 0.0,
        },
    }
    return doc


@pytest.fixture()
def ai_processed_ticket_doc(extracted_ticket_doc):
    """A ticket that has completed Stage B AI processing."""
    doc = dict(extracted_ticket_doc)
    doc["status"] = "ai_processed"
    doc["aiProcessing"] = {
        "status": "completed",
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "processingTimeMs": 3200,
        "agentName": "Information Processing Agent",
        "agentVersion": "1.0",
        "standardizedCodes": {
            "vendorCode": "VND-ABC",
            "productCodes": ["VLV-4200-IND", "SK-HP-4200"],
            "departmentCode": "DEPT-PROC",
            "costCenter": "CC-MFG-001",
        },
        "summary": "Standard invoice from ABC Industrial for valve assemblies.",
        "nextAction": "invoice_processing",
        "flags": [],
        "confidence": 0.92,
    }
    return doc


@pytest.fixture()
def sample_pdf_bytes():
    """Real PDF bytes from the first sample invoice (if available)."""
    pdf_path = SAMPLE_PDFS_DIR / "INV_ABC_Industrial_2026_78432.pdf"
    if pdf_path.exists():
        return pdf_path.read_bytes()
    # Fallback: create a minimal valid PDF for testing
    return _minimal_pdf()


def _minimal_pdf() -> bytes:
    """Generate a tiny valid PDF (1 page, minimal content) for tests."""
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "Test Invoice\nINVOICE NUMBER\nINV-TEST-001", fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
    except ImportError:
        # Absolute minimal valid PDF
        return (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Resources<<>>>>endobj\nxref\n0 4\n"
            b"0000000000 65535 f \n0000000009 00000 n \n"
            b"0000000058 00000 n \n0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n229\n%%EOF"
        )


@pytest.fixture()
def test_client(mock_settings):
    """
    FastAPI TestClient with Cosmos DB and Blob Storage fully mocked.

    The lifespan events (which would initialize real Azure connections)
    are patched out so tests run without any cloud credentials.
    """
    with patch("app.services.storage.initialize"), \
         patch("app.services.storage.close"), \
         patch("app.services.blob_storage.initialize_blob_storage"), \
         patch("app.services.blob_storage.close_blob_storage"):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            yield client
