"""
Stage A: Ingestion & Extraction service.

Two-approach extraction strategy:
  1. Python extraction (PyMuPDF/fitz) — fast, local
     Extracts: page count, file size, creation date, raw text preview.
  2. Azure Content Understanding — cloud AI, prebuilt-invoice analyzer
     Extracts: invoice number, vendor, amounts, line items, dates,
               confidence scores, and domain-specific fields.

When Content Understanding is not configured, falls back to a
regex-based simulation that parses the text extracted by PyMuPDF.
This lets the demo work end-to-end without cloud credentials.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import fitz  # PyMuPDF

from app.config import get_settings
from app.services import blob_storage, storage

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Step 1: Python Extraction (basic metadata via PyMuPDF)
# ═══════════════════════════════════════════════════════════════════

def extract_basic_metadata(pdf_bytes: bytes) -> dict:
    """
    Extract basic PDF metadata using PyMuPDF (fitz).

    Returns:
        dict with pageCount, fileSizeBytes, fileSizeDisplay,
        pdfCreationDate, rawTextPreview.
    """
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = doc.page_count
            file_size = len(pdf_bytes)

            # Human-readable file size
            if file_size < 1024:
                size_display = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_display = f"{file_size / 1024:.1f} KB"
            else:
                size_display = f"{file_size / (1024 * 1024):.2f} MB"

            # PDF creation date from metadata
            metadata = doc.metadata or {}
            creation_date = metadata.get("creationDate", "")
            # PDF dates look like "D:20260122103000+00'00'"
            parsed_date = _parse_pdf_date(creation_date) if creation_date else None

            # Extract raw text (first 2000 chars for preview)
            full_text = ""
            for page in doc:
                full_text += page.get_text()
                if len(full_text) > 5000:
                    break

            raw_text_preview = full_text[:2000].strip()

        return {
            "pageCount": page_count,
            "fileSizeBytes": file_size,
            "fileSizeDisplay": size_display,
            "pdfCreationDate": parsed_date,
            "rawTextPreview": raw_text_preview,
        }

    except Exception as e:
        logger.error("PyMuPDF extraction failed: %s", e)
        return {
            "pageCount": 0,
            "fileSizeBytes": len(pdf_bytes),
            "fileSizeDisplay": f"{len(pdf_bytes)} B",
            "pdfCreationDate": None,
            "rawTextPreview": "",
            "error": str(e),
        }


def extract_full_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF. Used by the fallback extractor."""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            text = ""
            for page in doc:
                text += page.get_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error("Full text extraction failed: %s", e)
        return ""


def _parse_pdf_date(date_str: str) -> Optional[str]:
    """Parse a PDF date string like ``D:20260122103000+00'00'`` to ISO with timezone."""
    try:
        # Strip the "D:" prefix
        cleaned = date_str.replace("D:", "").strip()
        # Parse the base datetime (YYYYMMDDHHMMSS)
        if len(cleaned) >= 14:
            dt = datetime.strptime(cleaned[:14], "%Y%m%d%H%M%S")
        elif len(cleaned) >= 8:
            dt = datetime.strptime(cleaned[:8], "%Y%m%d")
        else:
            return None

        # Parse timezone offset if present: +HH'MM' or -HH'MM' or Z
        tz_part = cleaned[14:] if len(cleaned) > 14 else ""
        tz_part = tz_part.replace("'", "")  # Remove apostrophes
        if tz_part:
            import re as _re
            tz_match = _re.match(r"([+-])(\d{2})(\d{2})", tz_part)
            if tz_match:
                sign = 1 if tz_match.group(1) == "+" else -1
                hours = int(tz_match.group(2))
                minutes = int(tz_match.group(3))
                from datetime import timedelta
                offset = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
                dt = dt.replace(tzinfo=offset)
            elif tz_part.startswith("Z"):
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            # No timezone info — assume UTC
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.isoformat()
    except (ValueError, IndexError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
# Step 2: Azure Content Understanding (prebuilt-invoice)
# ═══════════════════════════════════════════════════════════════════

def extract_with_content_understanding(
    blob_url: str,
    pdf_bytes: Optional[bytes] = None,
    extraction_method: str = "auto",
) -> dict:
    """
    Extract structured invoice data using Azure Content Understanding or regex fallback.

    Args:
        blob_url: SAS-signed URL to the PDF in Blob Storage.
        pdf_bytes: Raw PDF bytes (used for fallback text extraction).
        extraction_method: "cu" = force Content Understanding, "regex" = force
            regex fallback, "auto" = decide based on config.

    Returns:
        dict matching the ContentUnderstandingResult schema.
    """
    settings = get_settings()

    if extraction_method == "regex":
        # User explicitly requested fast regex extraction
        logger.info("Extraction method: regex (user-selected)")
        if pdf_bytes:
            return _extract_fallback(pdf_bytes)
        return _empty_cu_result("Regex extraction requested but no PDF bytes.")
    elif extraction_method == "cu":
        # User explicitly requested Content Understanding
        logger.info("Extraction method: Content Understanding (user-selected)")
        if settings.content_understanding_configured:
            result = _extract_with_cu_sdk(blob_url, settings)
            # Fix CU bug: compute line item amounts from qty × unitPrice when CU returns 0
            _fix_line_item_amounts(result)
            return result
        else:
            logger.warning("CU requested but not configured — falling back to regex")
            if pdf_bytes:
                return _extract_fallback(pdf_bytes)
            return _empty_cu_result("Content Understanding not configured and no PDF bytes.")
    else:
        # "auto" — original behavior based on config
        if settings.content_understanding_configured:
            result = _extract_with_cu_sdk(blob_url, settings)
            _fix_line_item_amounts(result)
            return result
        else:
            logger.warning(
                "Content Understanding not configured — using fallback text extraction."
            )
            if pdf_bytes:
                return _extract_fallback(pdf_bytes)
            return _empty_cu_result("Content Understanding not configured and no PDF bytes provided.")


def _fix_line_item_amounts(cu_result: dict) -> None:
    """Fix CU bug: compute amount = qty × unitPrice when CU returns 0."""
    line_items = cu_result.get("lineItems", [])
    for item in line_items:
        if not item.get("amount") or item["amount"] == 0:
            qty = item.get("quantity", 0) or 0
            unit_price = item.get("unitPrice", 0) or 0
            if qty and unit_price:
                item["amount"] = round(qty * unit_price, 2)


# ── Content Understanding client singleton ───────────────────────
_cu_client = None
_cu_client_endpoint = None
_cu_defaults_set = False


def _ensure_cu_defaults(client, settings):
    """Ensure Content Understanding default model deployments are configured.

    CU requires default model deployments to be set before using prebuilt
    analyzers. This maps our Azure AI Services model deployments to the
    model names that CU expects.
    """
    global _cu_defaults_set  # noqa: PLW0603
    if _cu_defaults_set:
        return

    try:
        # Map CU required model names → our deployment names
        model_deployments = {}
        model_name = settings.model_deployment_name or "gpt-5-mini"
        # CU needs gpt-4.1 for full analysis, text-embedding-3-large for embeddings
        model_deployments["gpt-4.1"] = "gpt-4.1"
        model_deployments["text-embedding-3-large"] = "text-embedding-3-large"
        client.update_defaults(model_deployments=model_deployments)
        _cu_defaults_set = True
        logger.info("Content Understanding defaults configured: %s", model_deployments)
    except Exception as e:
        # If defaults are already set, this might fail with a benign error
        logger.warning("Could not update CU defaults (may already be set): %s", e)
        _cu_defaults_set = True  # Don't retry on every request


def _get_cu_client(settings):
    """Return a singleton ContentUnderstandingClient, creating it on first use.

    Supports two authentication modes:
    - API key: when content_understanding_key is set
    - Managed Identity: when azure_client_id is set (no key needed)
    """
    global _cu_client, _cu_client_endpoint  # noqa: PLW0603

    # Re-create if endpoint changed (e.g. config reload in tests)
    if _cu_client is not None and _cu_client_endpoint == settings.content_understanding_endpoint:
        return _cu_client

    from azure.ai.contentunderstanding import ContentUnderstandingClient

    if settings.content_understanding_key:
        # API key auth
        from azure.core.credentials import AzureKeyCredential
        credential = AzureKeyCredential(settings.content_understanding_key)
        auth_mode = "API key"
    else:
        # Managed Identity auth
        from azure.identity import ManagedIdentityCredential
        credential = ManagedIdentityCredential(client_id=settings.azure_client_id)
        auth_mode = f"Managed Identity (client_id={settings.azure_client_id})"

    _cu_client = ContentUnderstandingClient(
        endpoint=settings.content_understanding_endpoint,
        credential=credential,
    )
    _cu_client_endpoint = settings.content_understanding_endpoint
    logger.info("Created Content Understanding client singleton for %s [auth: %s]", settings.content_understanding_endpoint, auth_mode)

    # Ensure CU model deployment defaults are configured
    _ensure_cu_defaults(_cu_client, settings)

    return _cu_client


def _extract_with_cu_sdk(blob_url: str, settings) -> dict:
    """Call Azure Content Understanding prebuilt-invoice analyzer."""
    try:
        from azure.ai.contentunderstanding.models import AnalyzeInput

        client = _get_cu_client(settings)

        logger.info("Starting Content Understanding analysis (prebuilt-invoice) url=%s...", blob_url[:80] if blob_url else "(empty)")

        # Begin analysis
        poller = client.begin_analyze(
            analyzer_id="prebuilt-invoice",
            inputs=[AnalyzeInput(url=blob_url)],
        )

        # Poll for result (SDK handles retries)
        result = poller.result()

        if not result.contents:
            logger.warning("Content Understanding returned no contents.")
            return _empty_cu_result("No contents returned from analyzer.")

        content = result.contents[0]

        # Convert CU model objects to plain Python dicts to avoid serialization issues
        # (CU returns NumberField, CurrencyField etc. which aren't JSON-serializable)
        content_dict = content.as_dict() if hasattr(content, "as_dict") else {}
        fields = content_dict.get("fields", {})

        logger.info("CU returned %d fields: %s", len(fields), list(fields.keys()))

        # ── Helper to safely extract field values from plain dicts ────
        def get_val(field_name: str, default=None):
            """Get simple field value (string, date, number, etc.)."""
            field = fields.get(field_name)
            if field is None:
                return default
            # Plain dict: look for value, valueString, valueDate, valueNumber
            if isinstance(field, dict):
                for key in ("value", "valueString", "valueDate", "valueNumber"):
                    if key in field and field[key] is not None:
                        return field[key]
            return default

        def get_amount_val(field_name: str) -> float:
            """Get amount from a currency field dict."""
            field = fields.get(field_name)
            if field is None:
                return 0.0
            if not isinstance(field, dict):
                return _to_float(field)
            # CU currency fields: {"Amount": {"valueNumber": X}, "CurrencyCode": {...}}
            # Or they can be in valueObject format
            val_obj = field.get("valueObject", field)
            if isinstance(val_obj, dict):
                amount_sub = val_obj.get("Amount", {})
                if isinstance(amount_sub, dict):
                    return _to_float(amount_sub.get("valueNumber", amount_sub.get("value")))
                return _to_float(amount_sub)
            return _to_float(field.get("valueNumber", field.get("value", 0)))

        def get_currency(field_name: str) -> str:
            """Extract currency code from a currency field dict."""
            field = fields.get(field_name)
            if field is None:
                return "USD"
            if not isinstance(field, dict):
                return "USD"
            val_obj = field.get("valueObject", field)
            if isinstance(val_obj, dict):
                cc = val_obj.get("CurrencyCode", {})
                if isinstance(cc, dict):
                    return cc.get("valueString", "USD") or "USD"
            return "USD"

        def get_conf(field_name: str) -> float:
            """Get confidence score for a field from plain dict."""
            field = fields.get(field_name)
            if field is None:
                return 0.0
            if isinstance(field, dict):
                # Direct confidence on the field
                if "confidence" in field and field["confidence"] is not None:
                    return float(field["confidence"])
                # Confidence might be inside sub-objects (for currency fields)
                val_obj = field.get("valueObject", field)
                if isinstance(val_obj, dict):
                    amount_sub = val_obj.get("Amount", {})
                    if isinstance(amount_sub, dict) and "confidence" in amount_sub:
                        return float(amount_sub["confidence"])
            return 0.0

        # ── Extract line items (CU field: LineItems) ─────────────
        line_items = []
        line_items_field = fields.get("LineItems")
        if line_items_field and isinstance(line_items_field, dict):
            items_list = line_items_field.get("valueArray", [])
        elif line_items_field and isinstance(line_items_field, list):
            items_list = line_items_field
        else:
            items_list = []

        for item in items_list:
            if isinstance(item, dict):
                item_obj = item.get("valueObject", item)
            else:
                item_obj = {}
            line_items.append({
                "description": _safe_dict_val(item_obj, "Description", ""),
                "productCode": _safe_dict_val(item_obj, "ProductCode", ""),
                "quantity": _safe_dict_val_num(item_obj, "Quantity", 0),
                "unitPrice": _safe_dict_val_num(item_obj, "UnitPrice", 0),
                "amount": _safe_dict_val_num(item_obj, "Amount", 0),
            })

        # ── Build result using corrected CU field names ──────────
        # CU prebuilt-invoice field name mapping:
        #   InvoiceId, VendorName, VendorAddress, InvoiceDate, DueDate,
        #   PONumber (not PurchaseOrder), PaymentTerm (not PaymentTerms),
        #   SubtotalAmount, TotalTaxAmount, TotalAmount (not InvoiceTotal),
        #   LineItems (not Items)
        cu_result = {
            "invoiceNumber": str(get_val("InvoiceId", "") or ""),
            "vendorName": str(get_val("VendorName", "") or ""),
            "vendorAddress": str(get_val("VendorAddress", "") or ""),
            "invoiceDate": str(get_val("InvoiceDate", "") or "") or None,
            "dueDate": str(get_val("DueDate", "") or "") or None,
            "poNumber": str(get_val("PONumber", "") or ""),
            "subtotal": get_amount_val("SubtotalAmount"),
            "taxAmount": get_amount_val("TotalTaxAmount"),
            "totalAmount": get_amount_val("TotalAmount") or get_amount_val("AmountDue"),
            "currency": get_currency("TotalAmount"),
            "paymentTerms": str(get_val("PaymentTerm", "") or ""),
            "lineItems": line_items,
            "confidenceScores": {
                "invoiceNumber": get_conf("InvoiceId"),
                "totalAmount": get_conf("TotalAmount"),
                "vendorName": get_conf("VendorName"),
                "overall": _avg_confidence(
                    get_conf("InvoiceId"),
                    get_conf("TotalAmount"),
                    get_conf("VendorName"),
                    get_conf("DueDate"),
                ),
            },
            "hazardousFlag": False,
            "dotClassification": "",
            "billOfLading": "",
            "hazmatSurcharge": 0.0,
        }

        logger.info(
            "Content Understanding extraction complete: invoice=%s, vendor=%s, total=%s",
            cu_result["invoiceNumber"], cu_result["vendorName"], cu_result["totalAmount"],
        )
        return cu_result

    except ImportError:
        logger.error(
            "azure-ai-contentunderstanding package not installed. "
            "Install it with: pip install azure-ai-contentunderstanding"
        )
        return _empty_cu_result("azure-ai-contentunderstanding package not installed.")
    except Exception as e:
        logger.error("Content Understanding extraction failed: %s", e, exc_info=True)
        return _empty_cu_result(f"Content Understanding error: {e}")


def _safe_field_val(field_dict: dict, key: str, default=None):
    """Safely get a value from a CU field object dict."""
    field = field_dict.get(key)
    if field is None:
        return default
    if hasattr(field, "value"):
        return field.value
    if isinstance(field, dict):
        for k in ("valueString", "value", "valueDate"):
            if k in field and field[k] is not None:
                return field[k]
    return default


def _safe_dict_val(field_dict: dict, key: str, default="") -> str:
    """Extract a string value from a plain dict CU field."""
    field = field_dict.get(key)
    if field is None:
        return default
    if isinstance(field, dict):
        for k in ("valueString", "value"):
            if k in field and field[k] is not None:
                return str(field[k])
    if isinstance(field, str):
        return field
    return default


def _safe_dict_val_num(field_dict: dict, key: str, default=0) -> float:
    """Extract a numeric value from a plain dict CU field."""
    field = field_dict.get(key)
    if field is None:
        return default
    if isinstance(field, dict):
        # Direct valueNumber
        if "valueNumber" in field and field["valueNumber"] is not None:
            return _to_float(field["valueNumber"])
        # Nested amount object
        if "valueObject" in field:
            amount = field["valueObject"].get("Amount", {})
            if isinstance(amount, dict) and "valueNumber" in amount:
                return _to_float(amount["valueNumber"])
        if "value" in field and field["value"] is not None:
            return _to_float(field["value"])
    if isinstance(field, (int, float)):
        return float(field)
    return _to_float(default)


def _to_float(value) -> float:
    """Convert a value to float, handling None and strings."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _avg_confidence(*scores: float) -> float:
    """Compute average confidence, ignoring zeros."""
    valid = [s for s in scores if s > 0]
    return round(sum(valid) / len(valid), 4) if valid else 0.0


def _empty_cu_result(error_msg: str = "") -> dict:
    """Return an empty Content Understanding result with an error."""
    return {
        "invoiceNumber": "",
        "vendorName": "",
        "vendorAddress": "",
        "invoiceDate": None,
        "dueDate": None,
        "poNumber": "",
        "subtotal": 0.0,
        "taxAmount": 0.0,
        "totalAmount": 0.0,
        "currency": "USD",
        "paymentTerms": "",
        "lineItems": [],
        "confidenceScores": {
            "invoiceNumber": 0.0,
            "totalAmount": 0.0,
            "vendorName": 0.0,
            "overall": 0.0,
        },
        "hazardousFlag": False,
        "dotClassification": "",
        "billOfLading": "",
        "hazmatSurcharge": 0.0,
        "error": error_msg,
    }


# ═══════════════════════════════════════════════════════════════════
# Fallback: Regex-based extraction from PDF text
# ═══════════════════════════════════════════════════════════════════

def _extract_fallback(pdf_bytes: bytes) -> dict:
    """
    Fallback extraction using regex on the raw PDF text.
    Used when Azure Content Understanding is not configured.

    Handles the multi-line text format produced by reportlab PDFs
    where labels (INVOICE NUMBER, INVOICE DATE, etc.) and values
    are on separate lines.

    Produces simulated confidence scores (0.85-0.95 for demo realism).
    """
    text = extract_full_text(pdf_bytes)
    if not text:
        return _empty_cu_result("Could not extract text from PDF.")

    logger.info("Running fallback regex extraction on %d chars of text...", len(text))
    lines = text.split("\n")

    # ── Vendor name (first line of the document) ─────────────
    vendor_name = lines[0].strip() if lines else ""

    # ── Vendor address (line after "INVOICE" header) ─────────
    vendor_address = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "INVOICE" and i + 1 < len(lines):
            vendor_address = lines[i + 1].strip()
            break

    # ── Field-value extraction (columnar layout) ─────────────
    # PDF renders labels grouped, then values grouped in same order:
    #   INVOICE NUMBER  │  INVOICE DATE  │  DUE DATE  │  PO NUMBER
    #   INV-2026-78432  │  Jan 22, 2026  │  Feb 21    │  PO-2026-1150
    invoice_header = _extract_columnar_block(
        lines, ["INVOICE NUMBER", "INVOICE DATE", "DUE DATE", "PO NUMBER"],
    )
    invoice_number = invoice_header.get("INVOICE NUMBER", "")
    invoice_date = invoice_header.get("INVOICE DATE", "")
    due_date = invoice_header.get("DUE DATE", "")
    po_number = invoice_header.get("PO NUMBER", "")

    billing_block = _extract_columnar_block(
        lines, ["BILL TO", "PAYMENT TERMS"],
    )
    payment_terms = billing_block.get("PAYMENT TERMS", "")

    # Normalize dates to YYYY-MM-DD
    if invoice_date:
        invoice_date = _normalize_date(invoice_date)
    if due_date:
        due_date = _normalize_date(due_date)

    # ── Amounts (label on one line, $value on next line) ─────
    subtotal = _find_amount_next_line(lines, "Subtotal")
    tax_amount = _find_amount_next_line(lines, "Tax")
    total_amount = _find_amount_next_line(lines, "TOTAL DUE")
    hazmat_surcharge = _find_amount_next_line(lines, "Hazmat Surcharge")

    # ── Payment terms fallback (also appears as "Payment Terms: NET-30") ──
    if not payment_terms:
        terms_match = re.search(r"Payment\s+Terms[:\s]*(NET-\d+)", text, re.IGNORECASE)
        payment_terms = terms_match.group(1) if terms_match else ""

    # ── Line items ──────────────────────────────────────────
    line_items = _extract_line_items_multiline(lines)

    # ── Special fields ──────────────────────────────────────
    hazardous = bool(re.search(r"HAZARDOUS|Hazmat|DOT\s+Classification", text, re.IGNORECASE))
    dot_match = re.search(r"Class\s+(\d+\s*-\s*[A-Za-z ]+?)(?:\s+under|\n|$)", text)
    dot_class = dot_match.group(1).strip() if dot_match else ""
    bol_match = re.search(r"(?:Bill\s+of\s+Lading|BOL|B/L)\s*(?:#|Number|No\.?)?\s*[:\s]*([A-Z0-9-]+)", text, re.IGNORECASE)
    bol = bol_match.group(1).strip() if bol_match else ""

    # Simulated confidence scores for demo
    conf_inv = 0.93 if invoice_number else 0.0
    conf_total = 0.96 if total_amount else 0.0
    conf_vendor = 0.91 if vendor_name else 0.0
    conf_overall = _avg_confidence(conf_inv, conf_total, conf_vendor)

    result = {
        "invoiceNumber": invoice_number,
        "vendorName": vendor_name,
        "vendorAddress": vendor_address,
        "invoiceDate": invoice_date,
        "dueDate": due_date,
        "poNumber": po_number,
        "subtotal": subtotal,
        "taxAmount": tax_amount,
        "totalAmount": total_amount,
        "currency": "USD",
        "paymentTerms": payment_terms,
        "lineItems": line_items,
        "confidenceScores": {
            "invoiceNumber": conf_inv,
            "totalAmount": conf_total,
            "vendorName": conf_vendor,
            "overall": conf_overall,
        },
        "hazardousFlag": hazardous,
        "dotClassification": dot_class,
        "billOfLading": bol,
        "hazmatSurcharge": hazmat_surcharge,
    }

    logger.info(
        "Fallback extraction complete: invoice=%s, vendor=%s, total=%.2f, items=%d",
        invoice_number, vendor_name, total_amount, len(line_items),
    )
    return result


def _extract_columnar_block(lines: list[str], labels: list[str]) -> dict[str, str]:
    """
    Extract values from a columnar header block in the PDF text.

    PyMuPDF renders side-by-side columns as labels grouped first, then
    values grouped in the same order:
        Line N:   INVOICE NUMBER
        Line N+1: INVOICE DATE
        Line N+2: DUE DATE
        Line N+3: PO NUMBER
        Line N+4: INV-2026-78432       ← value for INVOICE NUMBER
        Line N+5: January 22, 2026     ← value for INVOICE DATE
        Line N+6: February 21, 2026    ← value for DUE DATE
        Line N+7: PO-2026-1150         ← value for PO NUMBER

    Args:
        lines: All text lines from the PDF.
        labels: Ordered list of label strings to look for.

    Returns:
        dict mapping each label to its extracted value.
    """
    # Find the line index of each label
    label_indices: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        for label in labels:
            if stripped == label.upper() and label not in label_indices:
                label_indices[label] = i
                break

    if not label_indices:
        return {label: "" for label in labels}

    # Sort labels by their position in the document
    sorted_pairs = sorted(label_indices.items(), key=lambda x: x[1])
    last_label_idx = sorted_pairs[-1][1]

    # Values start right after the last label, in the same order
    results: dict[str, str] = {}
    for offset, (label, _) in enumerate(sorted_pairs):
        value_idx = last_label_idx + 1 + offset
        if value_idx < len(lines):
            results[label] = lines[value_idx].strip()
        else:
            results[label] = ""

    # Fill in any labels that weren't found
    for label in labels:
        if label not in results:
            results[label] = ""

    return results


def _find_amount_next_line(lines: list[str], label: str) -> float:
    """
    Find a dollar amount associated with a label.

    In our PDFs, amounts appear as:
        Subtotal:       ← label line
        $12,500.00      ← amount on next line

    Also handles the case where the amount is on the same line:
        Subtotal: $12,500.00
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        if label.lower() in stripped.lower():
            # Check same line first
            amount_match = re.search(r"\$\s*([\d,]+\.?\d{0,2})", stripped)
            if amount_match:
                amount_str = amount_match.group(1).replace(",", "")
                try:
                    return float(amount_str)
                except ValueError:
                    pass
            # Check next line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                amount_match = re.search(r"\$\s*([\d,]+\.?\d{0,2})", next_line)
                if amount_match:
                    amount_str = amount_match.group(1).replace(",", "")
                    try:
                        return float(amount_str)
                    except ValueError:
                        pass
    return 0.0


def _normalize_date(date_str: str) -> str:
    """Normalize various date formats to YYYY-MM-DD."""
    for fmt in ("%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def _extract_line_items_multiline(lines: list[str]) -> list[dict]:
    """
    Extract line items from a multi-line PDF text format.

    Our reportlab PDFs have line items where each field is on its own line:
        <Description line 1>
        <Description line 2 (optional)>
        <PRODUCT-CODE>
        <Quantity>
        $<UnitPrice>
        $<Amount>

    The table section starts after a line containing "AMOUNT" and ends
    at a line containing "Subtotal" or "TOTAL".
    """
    items = []

    # Find the start of the items table (after the header row)
    table_start = None
    table_end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "AMOUNT" or stripped == "Amount":
            table_start = i + 1
        if table_start and ("Subtotal" in stripped or "TOTAL" in stripped):
            table_end = i
            break

    if table_start is None or table_end is None:
        return items

    # Collect the table lines
    table_lines = [l.strip() for l in lines[table_start:table_end] if l.strip()]

    # Parse items: scan for product codes and dollar amounts
    # Strategy: build "chunks" — each chunk starts with text (description)
    # and eventually contains a product code pattern and amounts.
    current_desc_parts = []
    current_code = ""
    amounts_buffer = []

    for line in table_lines:
        # Check if this is a product code (2-4 uppercase letters, then dash, then alphanumeric)
        # Must not end with a hyphen (that means the code wraps to the next line)
        if re.match(r"^[A-Z]{2,5}-[A-Z0-9-]+$", line) and not line.endswith("-"):
            current_code = line
            continue

        # Handle product code that wraps across two lines (e.g. "FRT-TRUCK-LB-" / "BT")
        if re.match(r"^[A-Z]{2,5}-[A-Z0-9-]+-$", line):
            current_code = line  # partial code, continued on next line
            continue

        # Continuation of a hyphen-split product code
        if current_code and current_code.endswith("-") and re.match(r"^[A-Z0-9]+$", line):
            current_code += line
            continue

        # Check if this is a dollar amount
        amount_match = re.match(r"^\$?([\d,]+\.\d{2})$", line)
        if amount_match:
            amounts_buffer.append(float(amount_match.group(1).replace(",", "")))

            # A complete item has: code + at least qty + unit_price + amount
            # But our PDFs have: qty, $unit_price, $amount (qty has no $)
            continue

        # Check if this is a bare number (quantity)
        qty_match = re.match(r"^(\d+)$", line)
        if qty_match and current_code:
            # This is the quantity
            amounts_buffer.append(float(qty_match.group(1)))
            continue

        # Otherwise it's a description line
        # If we already have a complete item pending, flush it
        if current_code and len(amounts_buffer) >= 3:
            qty = amounts_buffer[0]
            unit_price = amounts_buffer[1]
            amount = amounts_buffer[2]
            items.append({
                "description": " ".join(current_desc_parts),
                "productCode": current_code,
                "quantity": qty,
                "unitPrice": unit_price,
                "amount": amount,
            })
            current_desc_parts = []
            current_code = ""
            amounts_buffer = []

        current_desc_parts.append(line)

    # Flush the last item
    if current_code and len(amounts_buffer) >= 3:
        qty = amounts_buffer[0]
        unit_price = amounts_buffer[1]
        amount = amounts_buffer[2]
        items.append({
            "description": " ".join(current_desc_parts),
            "productCode": current_code,
            "quantity": qty,
            "unitPrice": unit_price,
            "amount": amount,
        })

    return items


# ═══════════════════════════════════════════════════════════════════
# Combined Extraction Pipeline
# ═══════════════════════════════════════════════════════════════════

def process_extraction(
    ticket_id: str,
    pdf_bytes: Optional[bytes] = None,
    blob_name: Optional[str] = None,
    extraction_method: str = "regex",
) -> dict:
    """
    Run the full Stage A extraction pipeline for a ticket.

    1. Run Python extraction (fast, local — PyMuPDF).
    2. Run Content Understanding extraction (or fallback).
    3. Combine results and update Cosmos DB.
    4. Set ticket status to 'extracted'.

    This is meant to be called from a FastAPI BackgroundTask
    after the ticket has been created with status 'ingested'.

    Args:
        ticket_id: The ticket to process.
        pdf_bytes: Raw PDF file bytes (if available in memory).
        blob_name: Blob name for SAS URL generation (if PDF is in blob storage).

    Returns:
        dict with extraction results.
    """
    start_time = time.perf_counter()
    logger.info("Starting Stage A extraction for ticket %s...", ticket_id)

    # Update status → extracting
    storage.update_ticket(ticket_id, {"status": "extracting"})

    try:
        # ── Step 1: Basic metadata via PyMuPDF ───────────────
        basic_metadata = {}
        if pdf_bytes:
            logger.info("  Step 1: Extracting basic metadata (PyMuPDF)...")
            basic_metadata = extract_basic_metadata(pdf_bytes)
            logger.info(
                "  → %d pages, %s",
                basic_metadata.get("pageCount", 0),
                basic_metadata.get("fileSizeDisplay", "?"),
            )

        # ── Step 2: Content Understanding (or fallback) ──────
        logger.info("  Step 2: Content Understanding extraction...")
        cu_result = {}

        # Try to generate a SAS URL for Content Understanding
        blob_url = None
        settings = get_settings()
        if blob_name and settings.blob_configured:
            try:
                blob_url = blob_storage.generate_sas_url(blob_name, expiry_hours=1)
            except Exception as e:
                logger.warning("Could not generate SAS URL: %s", e)

        cu_result = extract_with_content_understanding(
            blob_url=blob_url or "",
            pdf_bytes=pdf_bytes,
            extraction_method=extraction_method,
        )

        # ── Step 3: Combine and persist ──────────────────────
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        extraction_update = {
            "status": "extracted",
            "extraction": {
                "status": "completed",
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "processingTimeMs": elapsed_ms,
                "extractionMethod": extraction_method,
                "basicMetadata": basic_metadata,
                "contentUnderstanding": cu_result,
                "errorMessage": cu_result.get("error"),
            },
        }

        storage.update_ticket(ticket_id, extraction_update)

        logger.info(
            "✅ Stage A extraction complete for %s (%d ms): "
            "invoice=%s, vendor=%s, total=%.2f",
            ticket_id,
            elapsed_ms,
            cu_result.get("invoiceNumber", "?"),
            cu_result.get("vendorName", "?"),
            cu_result.get("totalAmount", 0),
        )

        # ── Auto-trigger Stage B AI Processing ───────────────
        try:
            from app.services.ai_processing import trigger_ai_processing
            logger.info("Auto-chain: triggering Stage B for %s...", ticket_id)

            # Write debug marker BEFORE calling Stage B
            storage.update_ticket(ticket_id, {
                "_autochain": {"stage": "calling_stage_b", "ts": datetime.now(timezone.utc).isoformat()}
            })

            ai_result = trigger_ai_processing(ticket_id)
            logger.info(
                "Auto-chain: Stage B done for %s  success=%s  keys=%s",
                ticket_id, ai_result.get("success"), list(ai_result.keys()),
            )

            # Write debug marker AFTER Stage B
            storage.update_ticket(ticket_id, {
                "_autochain": {
                    "stage": "stage_b_done",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "success": ai_result.get("success"),
                    "result_keys": list(ai_result.keys()),
                }
            })

            # ── Auto-trigger Stage C if next_action is invoice_processing ──
            if ai_result.get("success"):
                agent_out = ai_result.get("agentOutput") or {}
                next_act = (
                    agent_out.get("next_action", "")
                    or ai_result.get("nextAction", "")
                )
                # Normalize: agent sometimes returns "invoice_processing to proceed..."
                next_act_normalized = next_act.strip().lower().split()[0] if next_act else ""
                should_invoice = "invoice_processing" in next_act.lower() if next_act else False
                logger.info(
                    "Auto-chain: next_action='%s' normalized='%s' should_invoice=%s for %s",
                    next_act, next_act_normalized, should_invoice, ticket_id,
                )

                # Write debug marker with next_action
                storage.update_ticket(ticket_id, {
                    "_autochain": {
                        "stage": "checking_next_action",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "next_action": next_act,
                        "next_act_normalized": next_act_normalized,
                        "should_invoice": should_invoice,
                        "agent_out_keys": list(agent_out.keys()) if agent_out else [],
                    }
                })

                if should_invoice:
                    try:
                        from app.services.invoice_processing import trigger_invoice_processing

                        # Add a delay before Stage C to avoid 429 rate limits
                        # (Stage B just consumed tokens from the AI model;
                        #  30K TPM limit needs ~30s for the bucket to refill)
                        logger.info("Auto-chain: waiting 30s before Stage C to avoid rate limits...")
                        time.sleep(30)

                        logger.info("Auto-chain: triggering Stage C for %s...", ticket_id)

                        storage.update_ticket(ticket_id, {
                            "_autochain": {"stage": "calling_stage_c", "ts": datetime.now(timezone.utc).isoformat()}
                        })

                        inv_result = trigger_invoice_processing(ticket_id)
                        logger.info(
                            "Auto-chain: Stage C done for %s  success=%s",
                            ticket_id, inv_result.get("success"),
                        )

                        storage.update_ticket(ticket_id, {
                            "_autochain": {
                                "stage": "stage_c_done",
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "success": inv_result.get("success"),
                            }
                        })
                    except Exception as inv_err:
                        logger.error("Auto-chain Stage C FAILED for %s: %s", ticket_id, inv_err, exc_info=True)
                        storage.update_ticket(ticket_id, {
                            "_autochain": {
                                "stage": "stage_c_error",
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "error": str(inv_err)[:500],
                            }
                        })
                else:
                    logger.info("Auto-chain: skipping Stage C for %s (next_action='%s')", ticket_id, next_act)
                    storage.update_ticket(ticket_id, {
                        "_autochain": {
                            "stage": "skipped_stage_c",
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "next_action": next_act,
                        }
                    })
            else:
                logger.warning("Auto-chain: Stage B was not successful for %s", ticket_id)
                storage.update_ticket(ticket_id, {
                    "_autochain": {
                        "stage": "stage_b_not_success",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "ai_result": {k: str(v)[:200] for k, v in ai_result.items()},
                    }
                })
        except Exception as chain_err:
            logger.error("Auto-chain Stage B FAILED for %s: %s", ticket_id, chain_err, exc_info=True)
            try:
                storage.update_ticket(ticket_id, {
                    "_autochain": {
                        "stage": "stage_b_exception",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "error": str(chain_err)[:500],
                    }
                })
            except Exception:
                pass

        return extraction_update["extraction"]

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(
            "❌ Stage A extraction failed for %s: %s", ticket_id, e, exc_info=True,
        )

        error_update = {
            "status": "error",
            "extraction": {
                "status": "error",
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "processingTimeMs": elapsed_ms,
                "basicMetadata": basic_metadata if basic_metadata else None,
                "contentUnderstanding": None,
                "errorMessage": str(e),
            },
        }
        try:
            storage.update_ticket(ticket_id, error_update)
        except Exception as update_err:
            logger.error("Failed to persist error state: %s", update_err)

        return error_update["extraction"]
