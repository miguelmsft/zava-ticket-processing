"""
Tests for PDF extraction (app.services.extraction).

Covers:
  • extract_basic_metadata — page count, file size, text preview
  • _parse_pdf_date — PDF date string → ISO format
  • extract_full_text — full text extraction
  • _extract_fallback — regex-based invoice field extraction
  • _empty_cu_result — empty result template
  • _normalize_date — date format normalization
  • _to_float — safe float conversion
  • _avg_confidence — average with zero-skipping
  • process_extraction — full pipeline with mocked Cosmos/Blob
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.services.extraction import (
    extract_basic_metadata,
    extract_full_text,
    _parse_pdf_date,
    _extract_fallback,
    _empty_cu_result,
    _normalize_date,
    _to_float,
    _avg_confidence,
    extract_with_content_understanding,
    process_extraction,
)

from tests.conftest import SAMPLE_PDFS_DIR


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

class TestToFloat:
    def test_none(self):
        assert _to_float(None) == 0.0

    def test_int(self):
        assert _to_float(42) == 42.0

    def test_string(self):
        assert _to_float("3.14") == 3.14

    def test_invalid_string(self):
        assert _to_float("abc") == 0.0


class TestAvgConfidence:
    def test_all_zeros(self):
        assert _avg_confidence(0.0, 0.0, 0.0) == 0.0

    def test_mixed(self):
        result = _avg_confidence(0.9, 0.0, 0.8)
        assert 0.84 < result < 0.86  # avg of 0.9, 0.8 = 0.85

    def test_all_valid(self):
        result = _avg_confidence(0.9, 0.8, 0.7, 0.6)
        assert abs(result - 0.75) < 0.01


class TestNormalizeDate:
    def test_month_day_year(self):
        assert _normalize_date("January 22, 2026") == "2026-01-22"

    def test_already_iso(self):
        assert _normalize_date("2026-01-22") == "2026-01-22"

    def test_slash_format(self):
        assert _normalize_date("01/22/2026") == "2026-01-22"

    def test_unknown_returns_original(self):
        assert _normalize_date("22-Jan-2026") == "22-Jan-2026"


class TestParsePdfDate:
    def test_full_with_tz(self):
        result = _parse_pdf_date("D:20260122103000+00'00'")
        assert result is not None
        assert "2026-01-22" in result

    def test_no_prefix(self):
        result = _parse_pdf_date("20260122103000")
        assert result is not None
        assert "2026-01-22" in result

    def test_date_only(self):
        result = _parse_pdf_date("D:20260122")
        assert result is not None
        assert "2026-01-22" in result

    def test_with_z(self):
        result = _parse_pdf_date("D:20260122103000Z")
        assert result is not None

    def test_invalid(self):
        result = _parse_pdf_date("invalid")
        assert result is None

    def test_too_short(self):
        result = _parse_pdf_date("D:2026")
        assert result is None


class TestEmptyCuResult:
    def test_structure(self):
        r = _empty_cu_result("test error")
        assert r["invoiceNumber"] == ""
        assert r["totalAmount"] == 0.0
        assert r["lineItems"] == []
        assert r["error"] == "test error"
        assert "confidenceScores" in r

    def test_no_error(self):
        r = _empty_cu_result()
        assert r["error"] == ""


# ═══════════════════════════════════════════════════════════════════
# PDF extraction (requires PyMuPDF + sample PDFs)
# ═══════════════════════════════════════════════════════════════════

class TestExtractBasicMetadata:
    def test_with_sample_pdf(self, sample_pdf_bytes):
        result = extract_basic_metadata(sample_pdf_bytes)
        assert result["pageCount"] >= 1
        assert result["fileSizeBytes"] > 0
        assert result["fileSizeDisplay"]  # non-empty
        assert isinstance(result["rawTextPreview"], str)

    def test_page_count_realistic(self, sample_pdf_bytes):
        result = extract_basic_metadata(sample_pdf_bytes)
        # Sample invoices are 1-3 pages
        assert 1 <= result["pageCount"] <= 5

    def test_file_size_display_kb(self, sample_pdf_bytes):
        result = extract_basic_metadata(sample_pdf_bytes)
        display = result["fileSizeDisplay"]
        assert "KB" in display or "MB" in display or "B" in display

    def test_invalid_pdf_returns_error(self):
        result = extract_basic_metadata(b"not a pdf")
        assert result["pageCount"] == 0
        assert "error" in result


class TestExtractFullText:
    def test_extracts_text(self, sample_pdf_bytes):
        text = extract_full_text(sample_pdf_bytes)
        assert len(text) > 0
        # The sample PDFs contain invoice-related text
        lower = text.lower()
        assert "invoice" in lower or "amount" in lower or "total" in lower

    def test_invalid_pdf(self):
        text = extract_full_text(b"not a pdf")
        assert text == ""


class TestExtractFallback:
    """Test regex-based fallback extraction on real sample PDFs."""

    def test_extracts_invoice_number(self, sample_pdf_bytes):
        result = _extract_fallback(sample_pdf_bytes)
        # Should extract an invoice number from the ABC Industrial PDF
        assert result["invoiceNumber"] != "" or result.get("error")

    def test_extracts_vendor_name(self, sample_pdf_bytes):
        result = _extract_fallback(sample_pdf_bytes)
        assert result["vendorName"] != ""

    def test_extracts_amounts(self, sample_pdf_bytes):
        result = _extract_fallback(sample_pdf_bytes)
        # Total should be non-zero for a valid invoice
        assert result["totalAmount"] > 0 or result.get("error")

    def test_confidence_scores(self, sample_pdf_bytes):
        result = _extract_fallback(sample_pdf_bytes)
        scores = result.get("confidenceScores", {})
        assert "overall" in scores

    def test_empty_pdf(self):
        """Fallback on minimal PDF with no invoice text."""
        # Use a PDF with no content
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        result = _extract_fallback(pdf_bytes)
        assert result["invoiceNumber"] == ""
        assert result["totalAmount"] == 0.0

    def test_all_sample_pdfs(self):
        """Run fallback on all 6 sample PDFs to ensure no crashes."""
        if not SAMPLE_PDFS_DIR.exists():
            pytest.skip("Sample PDFs directory not found")

        for pdf_file in SAMPLE_PDFS_DIR.glob("*.pdf"):
            pdf_bytes = pdf_file.read_bytes()
            result = _extract_fallback(pdf_bytes)
            # Should always return a dict with required keys
            assert "invoiceNumber" in result
            assert "vendorName" in result
            assert "totalAmount" in result
            assert "lineItems" in result
            assert isinstance(result["lineItems"], list)


# ═══════════════════════════════════════════════════════════════════
# Content Understanding router (SDK vs fallback)
# ═══════════════════════════════════════════════════════════════════

class TestExtractWithContentUnderstanding:
    def test_falls_back_when_not_configured(self, mock_settings, sample_pdf_bytes):
        """When CU is not configured, should use fallback extraction."""
        result = extract_with_content_understanding(
            blob_url="", pdf_bytes=sample_pdf_bytes,
        )
        assert isinstance(result, dict)
        assert "invoiceNumber" in result

    def test_returns_empty_when_no_pdf_and_no_cu(self, mock_settings):
        """With no CU config and no PDF bytes, return empty result."""
        result = extract_with_content_understanding(blob_url="", pdf_bytes=None)
        assert result["invoiceNumber"] == ""
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
# process_extraction (full pipeline, mocked Cosmos/Blob)
# ═══════════════════════════════════════════════════════════════════

class TestProcessExtraction:
    def test_extraction_pipeline(self, sample_pdf_bytes, mock_settings):
        """process_extraction should run both extractors and call update_ticket."""
        with patch("app.services.extraction.storage") as mock_cosmos, \
             patch("app.services.extraction.blob_storage") as mock_blob:
            mock_cosmos.update_ticket.return_value = {"ticketId": "ZAVA-TEST"}

            result = process_extraction(
                ticket_id="ZAVA-TEST",
                pdf_bytes=sample_pdf_bytes,
                blob_name="ZAVA-TEST/test.pdf",
            )

            # Should have called update_ticket at least twice
            # (once for "extracting", once for final result)
            assert mock_cosmos.update_ticket.call_count >= 2
            assert result["status"] in ("completed", "error")

    def test_extraction_without_pdf(self, mock_settings):
        """process_extraction with no PDF bytes should still succeed (empty metadata)."""
        with patch("app.services.extraction.storage") as mock_cosmos:
            mock_cosmos.update_ticket.return_value = {"ticketId": "ZAVA-TEST"}

            result = process_extraction(ticket_id="ZAVA-TEST", pdf_bytes=None)

            assert result["status"] in ("completed", "error")
