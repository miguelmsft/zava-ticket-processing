"""
AI Processing Service — Backend integration with Stage B Azure Function.

Provides the bridge between the FastAPI backend and the Stage B
AI Information Processing Azure Function. Calls the function via HTTP
and updates ticket status based on the result.

In development mode (or when Azure Functions are unavailable), provides
a local simulation that uses the code_mappings.json reference data to
generate realistic AI processing results.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.services import storage

logger = logging.getLogger(__name__)

# Timeout for the Stage B function call (agent creation + MCP tools + LLM + cold start)
STAGE_B_TIMEOUT_SECONDS = 240

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

def _simulate_ai_processing(ticket: dict, ticket_id: str) -> dict:
    """
    Simulate Stage B processing locally using code_mappings.json.

    Reads the extraction data from the ticket and:
      1. Looks up vendor, product, and department codes
      2. Determines the next action based on flags/conditions
      3. Creates a realistic summary
      4. Persists the results to storage
    """
    start_time = time.perf_counter()
    mappings = _load_code_mappings()

    extraction = ticket.get("extraction", {})
    cu = extraction.get("contentUnderstanding", {})

    vendor_name = cu.get("vendorName", "Unknown Vendor")
    total_amount = cu.get("totalAmount", 0)
    invoice_number = cu.get("invoiceNumber", "N/A")
    due_date = cu.get("dueDate", "")
    hazardous = cu.get("hazardousFlag", False)
    line_items = cu.get("lineItems", [])

    # ── Step 1: Look up vendor code ──────────────────
    vendor_mappings = mappings.get("vendor_codes", {}).get("mappings", {})
    vendor_info = vendor_mappings.get(vendor_name, {})
    vendor_code = vendor_info.get("vendorCode", "UNKNOWN-000")
    vendor_approved = vendor_info.get("approved", True)

    # ── Step 2: Look up product codes ────────────────
    product_mappings = mappings.get("product_codes", {}).get("mappings", {})
    product_codes = []
    first_category = ""
    price_discrepancy_detected = False
    for item in line_items:
        raw_code = item.get("productCode", "")
        pinfo = product_mappings.get(raw_code, {})
        std_code = pinfo.get("standardCode", f"ZAVA-{raw_code}-STD")
        product_codes.append(std_code)
        if not first_category:
            first_category = pinfo.get("category", "General")
        # Check unit price against expected range
        expected_range = pinfo.get("expectedPriceRange", {})
        unit_price = item.get("unitPrice", 0)
        if expected_range and unit_price:
            range_min = expected_range.get("min", 0)
            range_max = expected_range.get("max", float("inf"))
            if unit_price < range_min or unit_price > range_max:
                price_discrepancy_detected = True

    # ── Step 3: Look up department code ──────────────
    dept_mappings = mappings.get("department_codes", {}).get("mappings", {})
    dept_info = dept_mappings.get(first_category, {})
    department_code = dept_info.get("departmentCode", "PROC-GEN-000")
    cost_center = dept_info.get("costCenter", "CC-0000")

    # ── Step 4: Determine next action & flags ────────
    action_mappings = mappings.get("action_codes", {}).get("mappings", {})
    flags: list[str] = []
    action_key = "valid_invoice_all_checks_pass"

    # Check for amount discrepancy: sum of line items vs stated subtotal/total
    subtotal = cu.get("subtotal", 0)
    computed_subtotal = sum(item.get("amount", 0) for item in line_items)
    amount_discrepancy = False
    if subtotal and computed_subtotal and abs(computed_subtotal - subtotal) > 0.01:
        amount_discrepancy = True

    if not vendor_approved:
        action_key = "vendor_not_approved"
        flags.append("UNAPPROVED_VENDOR")
    elif price_discrepancy_detected or amount_discrepancy:
        action_key = "amount_discrepancy_detected"
        flags.append("AMOUNT_DISCREPANCY")
        flags.append("MANUAL_REVIEW_REQUIRED")
    elif hazardous:
        action_key = "hazardous_materials_present"
        flags.append("HAZARDOUS")
        flags.append("EHS_REVIEW_REQUIRED")
    elif due_date:
        try:
            due_dt = datetime.fromisoformat(due_date)
            if due_dt.date() < datetime.now(timezone.utc).date():
                action_key = "past_due_invoice"
                flags.append("PAST_DUE")
                flags.append("EXPEDITED_PAYMENT")
        except (ValueError, TypeError):
            pass

    action_info = action_mappings.get(action_key, {})
    next_action = action_info.get("nextAction", "invoice_processing")

    # ── Step 5: Build summary ────────────────────────
    item_desc = ", ".join(i.get("description", "item") for i in line_items[:3])
    if len(line_items) > 3:
        item_desc += f" and {len(line_items) - 3} more"
    summary_parts = [
        f"Invoice {invoice_number} from {vendor_name} for ${total_amount:,.2f}.",
        f"Items: {item_desc}." if item_desc else "",
    ]
    if flags:
        summary_parts.append(f"Flags: {', '.join(flags)}.")
    summary_parts.append(
        f"Action: {action_info.get('description', next_action)}."
    )
    summary = " ".join(p for p in summary_parts if p)

    elapsed_ms = int((time.perf_counter() - start_time) * 1000) + 850  # simulate realistic latency

    # ── Step 6: Persist results ──────────────────────
    now = datetime.now(timezone.utc).isoformat()
    update_payload = {
        "status": "ai_processed",
        "aiProcessing": {
            "status": "completed",
            "completedAt": now,
            "agentName": "information-processing-agent (local-sim)",
            "agentVersion": "1",
            "standardizedCodes": {
                "vendorCode": vendor_code,
                "productCodes": product_codes,
                "departmentCode": department_code,
                "costCenter": cost_center,
            },
            "summary": summary,
            "nextAction": next_action,
            "flags": flags,
            "confidence": 0.78 if not vendor_approved else (0.85 if "AMOUNT_DISCREPANCY" in flags else 0.95),
            "processingTimeMs": elapsed_ms,
        },
    }
    storage.update_ticket(ticket_id, update_payload)

    logger.info(
        "Local AI simulation completed for %s in %d ms → %s",
        ticket_id, elapsed_ms, next_action,
    )
    return {"success": True, **update_payload}


def trigger_ai_processing(ticket_id: str) -> dict:
    """
    Trigger Stage B AI Processing for a ticket.

    Calls the Stage B Azure Function HTTP endpoint which runs the
    Foundry Agent V2 to standardize codes, create summary, and
    assign next action.

    In development mode or when the function is unreachable, falls
    back to a local simulation using code_mappings.json.

    This is designed to be called from a FastAPI BackgroundTask
    after extraction completes, or from a manual trigger endpoint.

    Args:
        ticket_id: The ticket to process.

    Returns:
        dict with processing result or error details.
    """
    settings = get_settings()
    start_time = time.perf_counter()

    logger.info("Triggering Stage B AI Processing for %s", ticket_id)

    # Validate the ticket is in the correct status
    ticket = storage.get_ticket(ticket_id)
    if not ticket:
        return {"error": f"Ticket '{ticket_id}' not found", "success": False}

    current_status = ticket.get("status", "")
    if current_status not in ("extracted", "ai_processing", "error"):
        return {
            "error": f"Ticket is in status '{current_status}', expected 'extracted'",
            "success": False,
            "ticketId": ticket_id,
            "currentStatus": current_status,
        }

    # Build the request to Stage B function
    function_url = settings.stage_b_url
    if not function_url:
        logger.warning("STAGE_B_FUNCTION_URL not configured — using local simulation")
        return _simulate_ai_processing(ticket, ticket_id)

    # In development mode with default localhost URL, use simulation
    # to avoid hanging on TCP connection timeouts
    if settings.is_development and "localhost" in function_url:
        logger.info("Development mode — using local AI processing simulation")
        return _simulate_ai_processing(ticket, ticket_id)

    headers = {"Content-Type": "application/json"}
    if settings.stage_b_function_key:
        headers["x-functions-key"] = settings.stage_b_function_key

    payload = {"ticketId": ticket_id}

    try:
        with httpx.Client(timeout=STAGE_B_TIMEOUT_SECONDS) as client:
            response = client.post(function_url, json=payload, headers=headers)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if response.status_code == 200:
            result = response.json()
            result["processingTimeMs"] = elapsed_ms
            logger.info(
                "Stage B completed for %s in %d ms (status=%s)",
                ticket_id, elapsed_ms, result.get("status", "unknown"),
            )

            # Note: Auto-chain to Stage C is handled by the caller
            # (extraction.py) after this function returns.

            return {"success": True, **result}

        elif response.status_code == 404:
            logger.error("Stage B: Ticket %s not found by function", ticket_id)
            return {"error": "Ticket not found by processing function", "success": False}

        elif response.status_code == 409:
            result = response.json()
            logger.warning("Stage B: Status conflict for %s: %s", ticket_id, result)
            return {"error": result.get("error", "Status conflict"), "success": False}

        else:
            # Retry once on 503 (cold start) before falling back
            if response.status_code == 503:
                logger.warning(
                    "Stage B function returned 503 for %s — retrying in %ds",
                    ticket_id, RETRY_503_DELAY_SECONDS,
                )
                import asyncio
                import time as _time
                _time.sleep(RETRY_503_DELAY_SECONDS)
                try:
                    with httpx.Client(timeout=STAGE_B_TIMEOUT_SECONDS) as retry_client:
                        retry_response = retry_client.post(function_url, json=payload, headers=headers)
                    if retry_response.status_code == 200:
                        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                        result = retry_response.json()
                        result["processingTimeMs"] = elapsed_ms
                        logger.info("Stage B retry succeeded for %s in %d ms", ticket_id, elapsed_ms)
                        return {"success": True, **result}
                except Exception as retry_err:
                    logger.warning("Stage B retry also failed: %s", retry_err)

            # Check if simulation fallback is disabled
            if settings.disable_simulation_fallback:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                error_msg = f"Stage B function returned {response.status_code} and simulation fallback is disabled"
                logger.error(error_msg)
                storage.update_ticket(ticket_id, {
                    "status": "error",
                    "aiProcessing": {
                        "status": "error",
                        "errorMessage": error_msg,
                        "processingTimeMs": elapsed_ms,
                    },
                })
                return {"error": error_msg, "success": False}

            logger.warning(
                "Stage B function returned %d for %s — falling back to local simulation. Response: %s",
                response.status_code, ticket_id, response.text[:200],
            )
            return _simulate_ai_processing(ticket, ticket_id)

    except httpx.TimeoutException:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = f"Stage B function timed out after {STAGE_B_TIMEOUT_SECONDS}s"
        logger.error(error_msg)

        # Set error status on the ticket
        storage.update_ticket(ticket_id, {
            "status": "error",
            "aiProcessing": {
                "status": "error",
                "errorMessage": error_msg,
                "processingTimeMs": elapsed_ms,
            },
        })
        return {"error": error_msg, "success": False}

    except httpx.ConnectError:
        logger.warning(
            "Could not connect to Stage B function at %s — falling back to local simulation",
            function_url,
        )
        return _simulate_ai_processing(ticket, ticket_id)

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = f"Stage B call failed: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Set error status on the ticket so the UI reflects the failure
        storage.update_ticket(ticket_id, {
            "status": "error",
            "aiProcessing": {
                "status": "error",
                "errorMessage": error_msg,
                "processingTimeMs": elapsed_ms,
            },
        })
        return {"error": error_msg, "success": False}
