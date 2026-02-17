"""
Stage B — AI Information Processing Agent: Pure Business Logic

Contains agent instructions, response parsing, and output formatting.
Zero dependency on Azure SDKs — used by both function_app.py (runtime)
and the test suite.
"""

import json
import re
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════
# Agent System Instructions
# ═══════════════════════════════════════════════════════════════════

AGENT_NAME = "information-processing-agent"

AGENT_INSTRUCTIONS_TEMPLATE = """You are an AI ticket processing agent for Zava Processing Inc.

## Your Role
You process tickets that have been through the extraction stage. Your job is to
standardize codes, create a concise summary, and assign the appropriate next action.

## Your Tools
1. **Cosmos DB MCP Server** — Read and update ticket data in the database.
   - Use `read_ticket` to read the full ticket document by ticketId.
   - Use `update_ticket` to write your processing results back.

## Code Mapping Reference Tables
Use the reference tables below to look up standardized codes. Do NOT call any
external API for code lookups — all mapping data is embedded here.

{code_mappings_data}

## Processing Steps

Given a ticket ID, perform these steps IN ORDER:

### Step 1: Read the ticket
Use the `read_ticket` MCP tool with the provided ticket_id to get the full document.
Extract the relevant data from the `extraction` section (specifically the
`contentUnderstanding` fields: vendorName, lineItems with productCodes, invoiceNumber,
totalAmount, dueDate, etc.).

### Step 2: Standardize codes using the Code Mapping Reference Tables
Look up codes from the embedded reference tables above:
- **vendor_codes**: Look up the vendor name (e.g., "ABC Industrial Supplies") to get the vendorCode, approval status, and payment terms.
- **product_codes**: Look up each product code from the line items (e.g., "VLV-4200-IND") to get standardized codes.
- **department_codes**: Look up the product category (e.g., "Valves & Flow Control") to get department and cost center.

From the results, extract:
- `vendorCode`: The standardized vendor code (e.g., "ABCIND-001")
- `productCodes`: List of standardized product codes (e.g., ["ZAVA-VLV-4200-IND-STD"])
- `departmentCode`: The department code (e.g., "PROC-MFG-001")
- `costCenter`: The cost center (e.g., "CC-4500")

### Step 3: Determine the next action
Based on the code mapping results and extracted data, determine the appropriate next action.
Look up the action_codes reference table:

- If the vendor is approved AND all amounts look correct → use "valid_invoice_all_checks_pass"
- If the vendor is NOT approved → use "vendor_not_approved"
- If the total amount seems unusually high or there's a discrepancy → use "amount_discrepancy_detected"
- If hazardous materials are present → use "hazardous_materials_present"
- If the invoice is past due → use "past_due_invoice"
- If the invoice looks like a duplicate of an existing one → use "duplicate_invoice_suspected"
- If the invoice amount exceeds the department budget threshold → use "budget_exceeded"

The result will tell you the `nextAction` to assign.

### Step 4: Create a summary
Write a 2-3 sentence summary that includes:
- Vendor name and invoice amount
- What items are being purchased (briefly)
- Any notable flags (hazardous, past due, amount discrepancy, unapproved vendor)
- The assigned next action and why

### Step 5: Write results back to Cosmos DB
Use the `update_ticket` MCP tool to update the ticket with:

```json
{{
  "status": "ai_processed",
  "aiProcessing": {{
    "status": "completed",
    "completedAt": "<current ISO timestamp>",
    "agentName": "information-processing-agent",
    "agentVersion": "1",
    "standardizedCodes": {{
      "vendorCode": "<vendor code>",
      "productCodes": ["<product code 1>", "<product code 2>"],
      "departmentCode": "<department code>",
      "costCenter": "<cost center>"
    }},
    "summary": "<your summary>",
    "nextAction": "<the action from code mapping>",
    "flags": ["<any flags like HAZARDOUS, PAST_DUE, etc.>"],
    "confidence": 0.95
  }}
}}
```

## Important Rules
- Always use the Code Mapping Reference Tables above to look up codes. Do NOT guess or make up codes.
- The `updates_json` parameter for `update_ticket` must be a valid JSON *string*.
- Be precise with vendor names — use the exact name from the extraction data.
- If a code is not found in the mapping, note it in the summary and set confidence lower.
- Always set the status to "ai_processed" after successful processing.
"""


def build_instructions_with_code_mappings(code_mappings_json: str) -> str:
    """Build final agent instructions with code mapping data embedded."""
    return AGENT_INSTRUCTIONS_TEMPLATE.format(code_mappings_data=code_mappings_json)


# Default instructions (without code mappings, for testing)
AGENT_INSTRUCTIONS = AGENT_INSTRUCTIONS_TEMPLATE.format(code_mappings_data="[Code mappings not loaded]")

# ═══════════════════════════════════════════════════════════════════
# Valid values for output validation
# ═══════════════════════════════════════════════════════════════════

VALID_NEXT_ACTIONS = {
    "invoice_processing",
    "manual_review",
    "vendor_approval",
    "budget_approval",
}

VALID_FLAGS = {
    "HAZARDOUS",
    "PAST_DUE",
    "EXPEDITED_PAYMENT",
    "AMOUNT_DISCREPANCY",
    "UNAPPROVED_VENDOR",
    "INTERNATIONAL_SHIPMENT",
    "MISSING_FIELDS",
    "EHS_REVIEW_REQUIRED",
    "DUPLICATE_SUSPECTED",
    "BUDGET_EXCEEDED",
}


# ═══════════════════════════════════════════════════════════════════
# Build the user message for the agent
# ═══════════════════════════════════════════════════════════════════

def build_agent_input(ticket_id: str) -> str:
    """
    Build the user message to send to the Information Processing Agent.

    Tells the agent which ticket to process. The agent then uses its
    MCP tools to read the ticket and embedded code mappings for lookups.
    """
    return (
        f"Process ticket '{ticket_id}'. "
        f"Read the ticket data using the read_ticket tool, "
        f"standardize all codes using the Code Mapping API, "
        f"create a summary, assign the next action, and write the results "
        f"back to the database using update_ticket. "
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
        dict with keys: success, summary, next_action, ticket_id, raw_output
    """
    result = {
        "success": False,
        "summary": "",
        "next_action": "",
        "ticket_id": "",
        "standardized_codes": {},
        "flags": [],
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
            if "aiProcessing" in parsed:
                ap = parsed["aiProcessing"]
                result["summary"] = ap.get("summary", "")
                result["next_action"] = ap.get("nextAction", "")
                codes = ap.get("standardizedCodes", {})
                result["standardized_codes"] = codes
                result["flags"] = ap.get("flags", [])
                result["success"] = True
            elif "summary" in parsed:
                result["summary"] = parsed.get("summary", "")
                result["next_action"] = parsed.get("nextAction", parsed.get("next_action", ""))
                result["standardized_codes"] = parsed.get("standardizedCodes", parsed.get("standardized_codes", {}))
                result["flags"] = parsed.get("flags", [])
                result["success"] = True
        except json.JSONDecodeError:
            pass

    # If no JSON was parsed, check for success indicators in text
    if not result["success"]:
        lower = output_text.lower()
        if any(phrase in lower for phrase in [
            "successfully updated",
            "ai_processed",
            "processing complete",
            "results have been written",
            "update_ticket",
            "updated the ticket",
            "updated ticket",
            "wrote results",
            "written to cosmos",
            "written back",
            "update completed",
            "actions taken",
            "standardized",
            "next action",
            "done. i read ticket",
            "processing results",
        ]):
            result["success"] = True
            result["summary"] = _extract_summary_from_text(output_text)
            # Try to extract next_action from text
            if not result["next_action"]:
                result["next_action"] = _extract_field_from_text(output_text, "next action")
            if not result["next_action"]:
                result["next_action"] = _extract_field_from_text(output_text, "nextAction")

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


def _extract_summary_from_text(text: str) -> str:
    """Extract a summary from unstructured agent text output."""
    # Look for lines that mention "summary" or look like a summary
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "summary" in line.lower() and ":" in line:
            # Return the content after "Summary:"
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
            # Maybe the summary is on the next line
            if i + 1 < len(lines) and lines[i + 1].strip():
                return lines[i + 1].strip()
    # Fallback: return the first substantive paragraph
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 50 and not stripped.startswith(("#", "-", "*", "```")):
            return stripped
    # Last resort: return first 300 chars
    return text[:300].strip() if text else ""


def _extract_field_from_text(text: str, field_name: str) -> str:
    """Extract a field value from unstructured text like 'Next Action: invoice_processing'."""
    pattern = re.compile(rf"{re.escape(field_name)}\s*[:=]\s*[\"']?([^\n\"',]+)", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return ""


# ═══════════════════════════════════════════════════════════════════
# Build fallback AI processing result (if agent call fails)
# ═══════════════════════════════════════════════════════════════════

def build_fallback_result(
    ticket_id: str,
    error_message: str,
    processing_time_ms: int = 0,
) -> dict:
    """
    Build a fallback aiProcessing update when the agent fails.

    Sets status to 'error' and preserves the error message for debugging.
    """
    return {
        "status": "error",
        "aiProcessing": {
            "status": "error",
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "processingTimeMs": processing_time_ms,
            "agentName": AGENT_NAME,
            "agentVersion": "1",
            "summary": "",
            "nextAction": None,
            "standardizedCodes": None,
            "flags": [],
            "confidence": 0.0,
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
        "status": "ai_processed",
        "agentName": AGENT_NAME,
        "processingTimeMs": processing_time_ms,
    }
