"""
Stage C — Invoice Processing Agent: Pure Business Logic

Contains agent instructions, response parsing, and output formatting
for the Invoice Processing Foundry Agent V2.
Zero dependency on Azure SDKs — used by both function_app.py (runtime)
and the test suite.
"""

import json
import re
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════
# Agent System Instructions
# ═══════════════════════════════════════════════════════════════════

AGENT_NAME = "invoice-processing-agent"

AGENT_INSTRUCTIONS = """You are an Invoice Processing agent for Zava Processing Inc.

## Your Role
You process tickets that have completed AI information processing (status == "ai_processed")
and whose next action is "invoice_processing". Your job is to validate the invoice,
submit it for payment if valid, and record all results back to the database.

## Your Tools
1. **Cosmos DB MCP Server** — Read and update ticket data in the database.
   - Use `read_ticket` to read the full ticket document by ticketId.
   - Use `update_ticket` to write your invoice processing results back.

2. **Payment Processing Functions** — Validate invoices and submit payments.
   - Use `validate_invoice` to validate all invoice fields before payment.
   - Use `submit_payment` to submit a validated invoice for payment.
   - Use `get_payment_status` to verify payment was accepted.

## Processing Steps

Given a ticket ID, perform these steps IN ORDER:

### Step 1: Read the ticket
Use the `read_ticket` MCP tool with the provided ticket_id to get the full document.
Extract the relevant data:
- From `extraction.contentUnderstanding`: invoiceNumber, vendorName, totalAmount, dueDate
- From `aiProcessing`: standardizedCodes (vendorCode), nextAction, flags

Verify that `aiProcessing.nextAction` is "invoice_processing". If it is NOT
"invoice_processing" (e.g., "manual_review", "vendor_approval", "budget_approval"),
then this ticket should NOT be processed for payment. Instead, write a result
indicating skipped processing and the reason.

### Step 2: Validate the invoice
Call the `validate_invoice` function with:
- `invoiceNumber`: from the extraction data
- `vendorCode`: from aiProcessing.standardizedCodes.vendorCode
- `amount`: the totalAmount from extraction
- `dueDate`: from the extraction data

Review the validation results:
- `allValid`: whether all checks passed
- `validations.invoiceNumberValid`: invoice number format is correct
- `validations.amountValid`: amount is within acceptable range
- `validations.dueDateValid`: due date is valid (may be past-due)
- `validations.vendorApproved`: vendor is on the approved list
- `validations.budgetAvailable`: amount is within vendor budget limit
- `readyForPayment`: overall readiness for payment submission
- `flags`: any special flags (e.g., EXPEDITED_PAYMENT, PAST_DUE)

### Step 3: Submit payment (if validated)
If `readyForPayment` is true, call the `submit_payment` function with:
- `invoiceNumber`: from extraction
- `vendorCode`: from standardized codes
- `vendorName`: from extraction
- `amount`: totalAmount
- `currency`: "USD"
- `dueDate`: from extraction
- `ticketId`: the ticket ID being processed
- `paymentMethod`: "ACH Transfer" (default)

Record the response:
- `paymentId`: the unique payment identifier
- `status`: "submitted" or "rejected"
- `expectedPaymentDate`: when payment will be processed
- `submittedAt`: timestamp of submission

If `readyForPayment` is false, do NOT submit payment. Instead record
which validations failed and why.

### Step 4: Write results back to Cosmos DB
Use the `update_ticket` MCP tool to update the ticket with:

```json
{
  "status": "invoice_processed",
  "invoiceProcessing": {
    "status": "completed",
    "completedAt": "<current ISO timestamp>",
    "agentName": "invoice-processing-agent",
    "agentVersion": "1",
    "validations": {
      "invoiceNumberValid": true,
      "amountCorrect": true,
      "dueDateValid": true,
      "vendorApproved": true,
      "budgetAvailable": true
    },
    "paymentSubmission": {
      "submitted": true,
      "paymentId": "<payment ID from API>",
      "submittedAt": "<timestamp>",
      "expectedPaymentDate": "<date>",
      "paymentMethod": "ACH Transfer"
    },
    "errors": []
  }
}
```

If validations failed, set status to "completed" but `paymentSubmission.submitted` to false,
and list the validation failures in `errors`. Still set the ticket status to "invoice_processed"
since the processing itself completed — it's the payment that was not submitted.

If the ticket's nextAction was NOT "invoice_processing", set:
```json
{
  "status": "invoice_processed",
  "invoiceProcessing": {
    "status": "skipped",
    "completedAt": "<timestamp>",
    "agentName": "invoice-processing-agent",
    "agentVersion": "1",
    "validations": null,
    "paymentSubmission": null,
    "errors": ["Ticket nextAction is '<actual action>', not 'invoice_processing'. Skipped."]
  }
}
```

## Field Name Mapping
IMPORTANT: The Payment API validation response uses different field names than the ticket schema.
When writing results to the ticket, use THESE field names (right column), NOT the API field names:
- API `amountValid` → Ticket `amountCorrect`
- API `invoiceNumberValid` → Ticket `invoiceNumberValid` (same)
- API `dueDateValid` → Ticket `dueDateValid` (same)
- API `vendorApproved` → Ticket `vendorApproved` (same)
- API `budgetAvailable` → Ticket `budgetAvailable` (same)

## Important Rules
- The `updates_json` parameter for `update_ticket` must be a valid JSON *string*.
- Always validate BEFORE submitting payment — never submit without validation.
- If the invoice number format is non-standard (e.g., "DC-2026-4410" instead of "INV-YYYY-NNNNN"),
  the validation API may flag it but it should still proceed if other checks pass and
  readyForPayment is true.
- Record ALL validation details — even passing ones — for audit trail.
- Always set the ticket status to "invoice_processed" when done, even if payment was not submitted.
"""

# ═══════════════════════════════════════════════════════════════════
# Valid values for output validation
# ═══════════════════════════════════════════════════════════════════

VALID_INVOICE_STATUSES = {
    "completed",
    "skipped",
    "error",
}

VALID_PAYMENT_STATUSES = {
    "submitted",
    "rejected",
    "not_submitted",
}


# ═══════════════════════════════════════════════════════════════════
# Build the user message for the agent
# ═══════════════════════════════════════════════════════════════════

def build_agent_input(ticket_id: str) -> str:
    """
    Build the user message to send to the Invoice Processing Agent.

    Tells the agent which ticket to process. The agent then uses its
    MCP and function tools to read the ticket, validate, and submit payment.
    """
    return (
        f"Process invoice for ticket '{ticket_id}'. "
        f"Read the ticket data using the read_ticket tool, "
        f"validate the invoice using the Payment API validateInvoice endpoint, "
        f"submit the payment using submitPayment if validation passes, "
        f"and write all results back to the database using update_ticket. "
        f"Use the current timestamp: {datetime.now(timezone.utc).isoformat()}"
    )


# ═══════════════════════════════════════════════════════════════════
# Parse and validate agent response
# ═══════════════════════════════════════════════════════════════════

def parse_agent_response(output_text: str) -> dict:
    """
    Parse the agent's output text and extract structured results.

    The agent writes results directly to Cosmos DB via MCP tools,
    so the output text is primarily a confirmation/summary. We parse
    it for logging and for returning to the caller.

    Returns:
        dict with keys: success, payment_submitted, payment_id, validations,
        errors, raw_output
    """
    result = {
        "success": False,
        "payment_submitted": False,
        "payment_id": "",
        "validations": {},
        "errors": [],
        "raw_output": output_text or "",
    }

    if not output_text:
        result["error"] = "Agent returned empty response"
        return result

    # Try to extract JSON block from the response
    json_block = _extract_json_block(output_text)
    if json_block:
        try:
            parsed = json.loads(json_block)
            # The agent may return the full update payload or a confirmation
            if "invoiceProcessing" in parsed:
                ip = parsed["invoiceProcessing"]
                result["validations"] = ip.get("validations", {})
                ps = ip.get("paymentSubmission", {})
                if ps:
                    result["payment_submitted"] = ps.get("submitted", False)
                    result["payment_id"] = ps.get("paymentId", ps.get("payment_id", ""))
                result["errors"] = ip.get("errors", [])
                result["invoice_status"] = ip.get("status", "")
                result["success"] = True
            elif "paymentSubmission" in parsed or "payment_submitted" in parsed:
                ps = parsed.get("paymentSubmission", parsed)
                result["payment_submitted"] = ps.get("submitted", ps.get("payment_submitted", False))
                result["payment_id"] = ps.get("paymentId", ps.get("payment_id", ""))
                result["validations"] = parsed.get("validations", {})
                result["errors"] = parsed.get("errors", [])
                result["success"] = True
            elif "validations" in parsed:
                result["validations"] = parsed.get("validations", {})
                result["errors"] = parsed.get("errors", [])
                result["success"] = True
        except json.JSONDecodeError:
            pass

    # If no JSON was parsed, check for success indicators in text
    if not result["success"]:
        lower = output_text.lower()
        if any(phrase in lower for phrase in [
            "successfully updated",
            "invoice_processed",
            "processing complete",
            "results have been written",
            "update_ticket",
            "payment submitted",
            "payment has been submitted",
            "updated the ticket",
            "updated ticket",
            "wrote results",
            "written to cosmos",
            "written back",
            "update completed",
            "invoice validated",
            "validation complete",
            "validations passed",
            "all checks pass",
            "submitted for payment",
            "done. i read",
            "actions taken",
        ]):
            result["success"] = True
            # Try to detect payment submission from text
            if any(p in lower for p in ["payment submitted", "payment has been submitted", "pay-"]):
                result["payment_submitted"] = True
                # Try to extract payment ID
                pay_match = re.search(r"(PAY-\d{4}-\d+)", output_text)
                if pay_match:
                    result["payment_id"] = pay_match.group(1)

        # Check for skipped processing
        if any(phrase in lower for phrase in [
            "skipped",
            "not invoice_processing",
            "manual_review",
            "vendor_approval",
            "budget_approval",
        ]):
            result["success"] = True
            result["invoice_status"] = "skipped"

    return result


def _extract_json_block(text: str) -> str:
    """Extract the first JSON object or code-block JSON from text."""
    # Try ```json ... ``` blocks first
    code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if code_block:
        return code_block.group(1)

    # Try bare JSON object
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        candidate = brace_match.group(0)
        # Basic validation: must have balanced braces
        if candidate.count("{") == candidate.count("}"):
            return candidate

    return ""


# ═══════════════════════════════════════════════════════════════════
# Build fallback invoice processing result (if agent call fails)
# ═══════════════════════════════════════════════════════════════════

def build_fallback_result(
    ticket_id: str,
    error_message: str,
    processing_time_ms: int = 0,
) -> dict:
    """
    Build a fallback invoiceProcessing update when the agent fails.

    Sets status to 'error' and preserves the error message for debugging.
    """
    return {
        "status": "error",
        "invoiceProcessing": {
            "status": "error",
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "processingTimeMs": processing_time_ms,
            "agentName": AGENT_NAME,
            "agentVersion": "1",
            "validations": None,
            "paymentSubmission": None,
            "errors": [error_message],
            "errorMessage": error_message,
        },
    }


def build_success_result(processing_time_ms: int = 0) -> dict:
    """
    Build a minimal success confirmation for the API response.

    The actual data has already been written to Cosmos DB by the agent.
    This is returned to the caller for status reporting.
    """
    return {
        "status": "invoice_processed",
        "agentName": AGENT_NAME,
        "processingTimeMs": processing_time_ms,
    }
