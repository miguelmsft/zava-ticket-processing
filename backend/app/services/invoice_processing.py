"""
Invoice Processing Service — Backend integration with Stage C Azure Function.

Provides the bridge between the FastAPI backend and the Stage C
Invoice Processing Azure Function. Calls the function via HTTP
and updates ticket status based on the result.

In development mode (or when Azure Functions are unavailable), provides
a local simulation that validates invoice fields and simulates payment
submission with realistic results.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.services import storage

logger = logging.getLogger(__name__)

# Timeout for the Stage C function call (agent creation + function tools + LLM + cold start)
STAGE_C_TIMEOUT_SECONDS = 240

# Retry delay on 503 (cold start) before falling back to simulation
RETRY_503_DELAY_SECONDS = 10

# ── Local code mappings cache ────────────────────────────────────
_code_mappings: dict | None = None


def _load_code_mappings() -> dict:
    """Load code_mappings.json for local simulation."""
    global _code_mappings
    if _code_mappings is not None:
        return _code_mappings
    data_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "code_mappings.json"
    )
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            _code_mappings = json.load(f)
    except FileNotFoundError:
        logger.warning("code_mappings.json not found at %s — using empty mappings", data_path)
        _code_mappings = {}
    return _code_mappings


# ═══════════════════════════════════════════════════════════════════
# Local simulation (used when Azure Functions are not available)
# ═══════════════════════════════════════════════════════════════════

def _simulate_invoice_processing(ticket: dict, ticket_id: str) -> dict:
    """
    Simulate Stage C invoice processing locally.

    Reads ticket data and:
      1. Validates invoice fields against code mappings
      2. Simulates payment submission if all checks pass
      3. Persists results to storage
    """
    start_time = time.perf_counter()
    mappings = _load_code_mappings()

    extraction = ticket.get("extraction", {})
    cu = extraction.get("contentUnderstanding", {})
    ai = ticket.get("aiProcessing", {})

    invoice_number = cu.get("invoiceNumber", "")
    vendor_name = cu.get("vendorName", "Unknown Vendor")
    total_amount = cu.get("totalAmount", 0)
    due_date = cu.get("dueDate", "")
    next_action = ai.get("nextAction", "")
    vendor_code = (ai.get("standardizedCodes") or {}).get("vendorCode", "")
    ai_flags = ai.get("flags", [])

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # ── Handle skipped processing ────────────────────
    if next_action and next_action != "invoice_processing":
        elapsed_ms = int((time.perf_counter() - start_time) * 1000) + 120
        update_payload = {
            "status": "invoice_processed",
            "invoiceProcessing": {
                "status": "skipped",
                "completedAt": now_iso,
                "agentName": "invoice-processing-agent (local-sim)",
                "agentVersion": "1",
                "validations": None,
                "paymentSubmission": None,
                "errors": [
                    f"Ticket nextAction is '{next_action}', not 'invoice_processing'. Skipped."
                ],
                "processingTimeMs": elapsed_ms,
            },
        }
        storage.update_ticket(ticket_id, update_payload)
        logger.info("Invoice processing skipped for %s — nextAction=%s", ticket_id, next_action)
        return {"success": True, **update_payload}

    # ── Step 1: Validate invoice fields ──────────────
    vendor_mappings = mappings.get("vendor_codes", {}).get("mappings", {})
    vendor_info = vendor_mappings.get(vendor_name, {})
    vendor_approved = vendor_info.get("approved", True)

    # Check due date validity
    due_date_valid = True
    past_due = False
    if due_date:
        try:
            due_dt = datetime.fromisoformat(due_date)
            if due_dt.date() < now.date():
                past_due = True
            due_date_valid = True  # Date is parseable
        except (ValueError, TypeError):
            due_date_valid = False

    # Invoice number format check
    invoice_number_valid = bool(invoice_number) and (
        invoice_number.startswith("INV-") or
        invoice_number.startswith("DC-") or
        invoice_number.startswith("FRT-") or
        len(invoice_number) > 5
    )

    # Amount checks
    amount_valid = total_amount > 0 and total_amount < 500_000
    budget_available = total_amount < 100_000  # Simplified budget check

    validations = {
        "invoiceNumberValid": invoice_number_valid,
        "amountCorrect": amount_valid,
        "dueDateValid": due_date_valid,
        "vendorApproved": vendor_approved,
        "budgetAvailable": budget_available,
    }

    all_valid = all(validations.values())
    errors: list[str] = []

    if not invoice_number_valid:
        errors.append(f"Invoice number '{invoice_number}' has invalid format.")
    if not amount_valid:
        errors.append(f"Amount ${total_amount:,.2f} is outside acceptable range.")
    if not due_date_valid:
        errors.append(f"Due date '{due_date}' is not a valid date.")
    if not vendor_approved:
        errors.append(f"Vendor '{vendor_name}' is not on the approved vendor list.")
    if not budget_available:
        errors.append(f"Amount ${total_amount:,.2f} exceeds department budget threshold.")

    # ── Step 2: Submit payment (if valid) ────────────
    payment_submission: dict
    if all_valid:
        payment_id = f"PAY-{now.strftime('%Y%m%d')}-{random.randint(10000, 99999)}"
        expected_date = (now + timedelta(days=3 if not past_due else 1)).strftime("%Y-%m-%d")
        payment_submission = {
            "submitted": True,
            "paymentId": payment_id,
            "submittedAt": now_iso,
            "expectedPaymentDate": expected_date,
            "paymentMethod": "ACH Transfer",
            "status": "submitted",
        }
    else:
        payment_submission = {
            "submitted": False,
            "paymentId": None,
            "submittedAt": None,
            "expectedPaymentDate": None,
            "paymentMethod": None,
            "status": "not_submitted",
        }

    elapsed_ms = int((time.perf_counter() - start_time) * 1000) + 1200  # simulate realistic latency

    # ── Step 3: Persist results ──────────────────────
    update_payload = {
        "status": "invoice_processed",
        "invoiceProcessing": {
            "status": "completed",
            "completedAt": now_iso,
            "agentName": "invoice-processing-agent (local-sim)",
            "agentVersion": "1",
            "validations": validations,
            "paymentSubmission": payment_submission,
            "errors": errors,
            "processingTimeMs": elapsed_ms,
        },
    }
    storage.update_ticket(ticket_id, update_payload)

    status_word = "submitted" if all_valid else "rejected"
    logger.info(
        "Local invoice simulation completed for %s in %d ms → payment %s",
        ticket_id, elapsed_ms, status_word,
    )
    return {"success": True, **update_payload}


def trigger_invoice_processing(ticket_id: str) -> dict:
    """
    Trigger Stage C Invoice Processing for a ticket.

    Calls the Stage C Azure Function HTTP endpoint which runs the
    Foundry Agent V2 to validate the invoice, submit payment if valid,
    and record all results.

    This is designed to be called from a FastAPI BackgroundTask
    after AI processing completes, or from a manual trigger endpoint.

    Args:
        ticket_id: The ticket to process.

    Returns:
        dict with processing result or error details.
    """
    settings = get_settings()
    start_time = time.perf_counter()

    logger.info("Triggering Stage C Invoice Processing for %s", ticket_id)

    # Validate the ticket is in the correct status
    ticket = storage.get_ticket(ticket_id)
    if not ticket:
        return {"error": f"Ticket '{ticket_id}' not found", "success": False}

    current_status = ticket.get("status", "")
    if current_status not in ("ai_processed", "invoice_processing", "error"):
        return {
            "error": f"Ticket is in status '{current_status}', expected 'ai_processed'",
            "success": False,
            "ticketId": ticket_id,
            "currentStatus": current_status,
        }

    # Build the request to Stage C function
    function_url = settings.stage_c_url
    if not function_url:
        logger.warning("STAGE_C_FUNCTION_URL not configured — using local simulation")
        return _simulate_invoice_processing(ticket, ticket_id)

    # In development mode with default localhost URL, use simulation
    # to avoid hanging on TCP connection timeouts
    if settings.is_development and "localhost" in function_url:
        logger.info("Development mode — using local invoice processing simulation")
        return _simulate_invoice_processing(ticket, ticket_id)

    headers = {"Content-Type": "application/json"}
    if settings.stage_c_function_key:
        headers["x-functions-key"] = settings.stage_c_function_key

    payload = {"ticketId": ticket_id}

    try:
        with httpx.Client(timeout=STAGE_C_TIMEOUT_SECONDS) as client:
            response = client.post(function_url, json=payload, headers=headers)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if response.status_code == 200:
            result = response.json()
            result["processingTimeMs"] = elapsed_ms
            logger.info(
                "Stage C completed for %s in %d ms (status=%s)",
                ticket_id, elapsed_ms, result.get("status", "unknown"),
            )
            return {"success": True, **result}

        elif response.status_code == 404:
            logger.error("Stage C: Ticket %s not found by function", ticket_id)
            return {"error": "Ticket not found by processing function", "success": False}

        elif response.status_code == 409:
            result = response.json()
            logger.warning("Stage C: Status conflict for %s: %s", ticket_id, result)
            return {"error": result.get("error", "Status conflict"), "success": False}

        else:
            # Retry once on 503 (cold start) before falling back
            if response.status_code == 503:
                logger.warning(
                    "Stage C function returned 503 for %s — retrying in %ds",
                    ticket_id, RETRY_503_DELAY_SECONDS,
                )
                import time as _time
                _time.sleep(RETRY_503_DELAY_SECONDS)
                try:
                    with httpx.Client(timeout=STAGE_C_TIMEOUT_SECONDS) as retry_client:
                        retry_response = retry_client.post(function_url, json=payload, headers=headers)
                    if retry_response.status_code == 200:
                        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                        result = retry_response.json()
                        result["processingTimeMs"] = elapsed_ms
                        logger.info("Stage C retry succeeded for %s in %d ms", ticket_id, elapsed_ms)
                        return {"success": True, **result}
                except Exception as retry_err:
                    logger.warning("Stage C retry also failed: %s", retry_err)

            # Check if simulation fallback is disabled
            if settings.disable_simulation_fallback:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                error_msg = f"Stage C function returned {response.status_code} and simulation fallback is disabled"
                logger.error(error_msg)
                storage.update_ticket(ticket_id, {
                    "status": "error",
                    "invoiceProcessing": {
                        "status": "error",
                        "errorMessage": error_msg,
                        "processingTimeMs": elapsed_ms,
                    },
                })
                return {"error": error_msg, "success": False}

            logger.warning(
                "Stage C function returned %d for %s — falling back to local simulation. Response: %s",
                response.status_code, ticket_id, response.text[:200],
            )
            return _simulate_invoice_processing(ticket, ticket_id)

    except httpx.TimeoutException:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = f"Stage C function timed out after {STAGE_C_TIMEOUT_SECONDS}s"
        logger.error(error_msg)

        # Set error status on the ticket
        storage.update_ticket(ticket_id, {
            "status": "error",
            "invoiceProcessing": {
                "status": "error",
                "errorMessage": error_msg,
                "processingTimeMs": elapsed_ms,
            },
        })
        return {"error": error_msg, "success": False}

    except httpx.ConnectError:
        logger.warning(
            "Could not connect to Stage C function at %s — falling back to local simulation",
            function_url,
        )
        return _simulate_invoice_processing(ticket, ticket_id)

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = f"Stage C call failed: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Set error status on the ticket so the UI reflects the failure
        storage.update_ticket(ticket_id, {
            "status": "error",
            "invoiceProcessing": {
                "status": "error",
                "errorMessage": error_msg,
                "processingTimeMs": elapsed_ms,
            },
        })
        return {"error": error_msg, "success": False}
