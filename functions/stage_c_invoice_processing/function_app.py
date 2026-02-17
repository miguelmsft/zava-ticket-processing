"""
Stage C — Invoice Processing Agent (Azure Function)

Processes tickets that have completed AI information processing
(status == "ai_processed", nextAction == "invoice_processing")
by running a Foundry Agent V2 that validates invoices, submits
payments via the Payment API, and records all results.

Triggers:
  HTTP POST /api/process-invoice  — Trigger processing for a specific ticket
    Body: {"ticketId": "ZAVA-2026-00001"}

In production this would be a Cosmos DB Change Feed trigger that fires
automatically when a ticket reaches "ai_processed" status with
nextAction == "invoice_processing". For the demo we use an HTTP
trigger so the UI can control timing.

The agent uses two tool types:
  • MCP Tool      → Cosmos DB MCP Server (read/write ticket data)
  • Function Tools → Payment Processing API (validate & submit invoices)

SDK: azure-ai-projects >= 2.0.0b3 (Foundry Agent V2 — Responses API)
"""

import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone

import azure.functions as func
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential, AzureCliCredential

from invoice_agent_logic import (
    AGENT_NAME,
    AGENT_INSTRUCTIONS,
    build_agent_input,
    parse_agent_response,
    build_fallback_result,
    build_success_result,
)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# OpenTelemetry Tracing
# Note: Azure Functions host handles App Insights export automatically
# via APPLICATIONINSIGHTS_CONNECTION_STRING. We only create a tracer
# here for custom span creation — do NOT call configure_azure_monitor()
# as it conflicts with the Functions host startup and causes timeouts.
# ═══════════════════════════════════════════════════════════════════
try:
    from opentelemetry import trace as otel_trace
    _tracer = otel_trace.get_tracer(__name__)
    logger.info("OpenTelemetry tracer initialized for Stage C")
except Exception as _otel_err:
    logging.getLogger(__name__).warning("OpenTelemetry init skipped: %s", _otel_err)
    # Fallback no-op tracer so span context manager still works
    from contextlib import contextmanager
    class _NoOpTracer:
        @contextmanager
        def start_as_current_span(self, name, **kwargs):
            yield None
    _tracer = _NoOpTracer()

# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════

AI_PROJECT_ENDPOINT = os.environ.get("AI_PROJECT_ENDPOINT", "")
MODEL_DEPLOYMENT_NAME = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o")

MCP_COSMOS_ENDPOINT = os.environ.get("MCP_COSMOS_ENDPOINT", "")
MCP_COSMOS_KEY = os.environ.get("MCP_COSMOS_KEY", "")

PAYMENT_API_ENDPOINT = os.environ.get("PAYMENT_API_URL", os.environ.get("PAYMENT_API_ENDPOINT", ""))
PAYMENT_API_KEY = os.environ.get("PAYMENT_API_KEY", "")

COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_KEY = os.environ.get("COSMOS_KEY", "")
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "zava-ticket-processing")
COSMOS_USE_EMULATOR = os.environ.get("COSMOS_USE_EMULATOR", "false").lower() == "true"

# ═══════════════════════════════════════════════════════════════════
# Cosmos DB direct client (for status updates outside the agent)
# ═══════════════════════════════════════════════════════════════════

_cosmos_client = None


def _get_cosmos_client():
    """Return singleton CosmosClient for direct status updates."""
    global _cosmos_client
    if _cosmos_client is None:
        kwargs = {}
        if COSMOS_USE_EMULATOR:
            kwargs["connection_verify"] = False
        credential = COSMOS_KEY if COSMOS_KEY else DefaultAzureCredential()
        _cosmos_client = CosmosClient(
            url=COSMOS_ENDPOINT,
            credential=credential,
            **kwargs,
        )
    return _cosmos_client


def _get_tickets_container():
    """Return the tickets container proxy."""
    db = _get_cosmos_client().get_database_client(COSMOS_DATABASE)
    return db.get_container_client("tickets")


def _update_ticket_status(ticket_id: str, updates: dict):
    """Direct Cosmos DB update for status transitions."""
    container = _get_tickets_container()
    try:
        current = container.read_item(item=ticket_id, partition_key=ticket_id)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(current.get(key), dict):
                _deep_merge(current[key], value)
            else:
                current[key] = value
        current["updatedAt"] = datetime.now(timezone.utc).isoformat()
        container.upsert_item(body=current)
        logger.info("Updated ticket %s status directly", ticket_id)
    except exceptions.CosmosResourceNotFoundError:
        logger.error("Ticket %s not found for status update", ticket_id)
    except Exception as e:
        logger.error("Failed to update ticket %s: %s", ticket_id, e)


def _deep_merge(base: dict, updates: dict) -> dict:
    """Recursive dict merge (same as cosmos_helpers.deep_merge)."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# ═══════════════════════════════════════════════════════════════════
# Function Tool definitions for Payment API (client-side execution)
# ═══════════════════════════════════════════════════════════════════

# Foundry Agent V2 requires ALL tools to be in the agent definition
# when using agent_reference.  Payment API tools are defined here and
# included in the agent definition.  At runtime, the agent emits
# function_call outputs which we execute client-side against the
# Payment API and feed back via the tool-call loop.

PAYMENT_FUNCTION_TOOLS = [
    {
        "type": "function",
        "name": "validate_invoice",
        "description": (
            "Validate an invoice before payment submission. Checks invoice number "
            "format, amount ranges, due date validity, vendor approval status, and "
            "budget availability. Always call this before submitting payment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "invoiceNumber": {
                    "type": "string",
                    "description": "Invoice number from the ticket (e.g., 'INV-2026-78432')",
                },
                "vendorCode": {
                    "type": "string",
                    "description": "Standardized vendor code from AI processing (e.g., 'OCEFRT-005')",
                },
                "amount": {
                    "type": "number",
                    "description": "Total invoice amount in USD",
                },
                "dueDate": {
                    "type": "string",
                    "description": "Invoice due date in ISO format (e.g., '2026-03-15')",
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code (default USD)",
                    "default": "USD",
                },
            },
            "required": ["invoiceNumber", "vendorCode", "amount", "dueDate"],
        },
    },
    {
        "type": "function",
        "name": "submit_payment",
        "description": (
            "Submit a validated invoice for payment via ACH transfer. "
            "Only call this after successful validation (readyForPayment=true)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "invoiceNumber": {
                    "type": "string",
                    "description": "Invoice number",
                },
                "vendorCode": {
                    "type": "string",
                    "description": "Standardized vendor code",
                },
                "vendorName": {
                    "type": "string",
                    "description": "Full vendor name",
                },
                "amount": {
                    "type": "number",
                    "description": "Total payment amount",
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code (default USD)",
                    "default": "USD",
                },
                "dueDate": {
                    "type": "string",
                    "description": "Invoice due date",
                },
                "ticketId": {
                    "type": "string",
                    "description": "Associated ticket ID",
                },
                "paymentMethod": {
                    "type": "string",
                    "description": "Payment method (default 'ACH Transfer')",
                    "default": "ACH Transfer",
                },
            },
            "required": ["invoiceNumber", "vendorCode", "vendorName", "amount", "dueDate", "ticketId"],
        },
    },
    {
        "type": "function",
        "name": "get_payment_status",
        "description": "Check the status of a submitted payment by its payment ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "payment_id": {
                    "type": "string",
                    "description": "The payment ID returned from submit_payment",
                },
            },
            "required": ["payment_id"],
        },
    },
]


# ═══════════════════════════════════════════════════════════════════
# Foundry Agent V2 — Persistent agent lifecycle & execution
# ═══════════════════════════════════════════════════════════════════

# Module-level cache: holds the persistent agent reference across requests
# within the same function app process. Avoids re-creating agents on every call.
_cached_agent = None


def _ensure_agent_exists(project_client) -> object:
    """
    Ensure a persistent Foundry Agent V2 exists and return it.

    Uses a create-once / reuse-many pattern:
      1. If cached agent exists → verify it still exists via get() → return
      2. If cache is stale (404 on get) → clear cache, fall through
      3. If cache is empty → create() the agent → cache and return
      4. If create() fails with 409 (already exists) → get() and cache

    This ensures agents persist across requests and are visible in the
    Foundry portal at https://ai.azure.com.
    """
    from azure.ai.projects.models import (
        PromptAgentDefinition,
        MCPTool,
    )

    global _cached_agent

    # ── Try cached agent first ────────────────────────
    if _cached_agent is not None:
        try:
            agent = project_client.agents.get(agent_name=_cached_agent.name)
            logger.info("Using cached agent: %s (id=%s)", agent.name, agent.id)
            return agent
        except Exception as e:
            logger.warning("Cached agent stale (%s), will re-create", e)
            _cached_agent = None

    # ── Build the agent definition ────────────────────
    mcp_tool = MCPTool(
        server_label="cosmos-db-tickets",
        server_url=MCP_COSMOS_ENDPOINT,
        require_approval="never",
    )

    # Agent definition includes BOTH tool types:
    #   • MCP Tool      → Cosmos DB (server-side, auto-approved)
    #   • Function Tools → Payment API (client-side, executed in tool-call loop)
    # This is required because responses.create() with agent_reference
    # does not allow additional tools at request time.
    definition = PromptAgentDefinition(
        model=MODEL_DEPLOYMENT_NAME,
        instructions=AGENT_INSTRUCTIONS,
        tools=[mcp_tool, *PAYMENT_FUNCTION_TOOLS],
    )

    # ── Create or retrieve the persistent agent ───────
    try:
        logger.info("Creating persistent Foundry Agent V2: %s", AGENT_NAME)
        agent = project_client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=definition,
            description="Invoice Processing Agent for Zava Processing ticket pipeline",
        )
        logger.info("Agent created: %s (id=%s, version=%s)", agent.name, agent.id, getattr(agent, 'version', '?'))
    except Exception as create_err:
        # Agent may already exist — try to list versions to get the latest
        logger.info(
            "Agent create_version returned error (%s: %s), attempting list_versions()",
            type(create_err).__name__, str(create_err)[:200],
        )
        try:
            versions = list(project_client.agents.list_versions(agent_name=AGENT_NAME))
            if versions:
                agent = versions[-1]
                logger.info("Found existing agent version: %s v%s", agent.name, getattr(agent, 'version', '?'))
            else:
                logger.error("No versions found for agent %s", AGENT_NAME)
                raise create_err
        except Exception as list_err:
            logger.error("Failed to create or list agent versions: create=%s, list=%s", create_err, list_err)
            raise create_err

    _cached_agent = agent
    return agent


def _create_and_run_agent(ticket_id: str) -> dict:
    """
    Run the persistent Foundry Agent V2 against a ticket for invoice processing.

    Steps:
      1. Initialize AIProjectClient
      2. Ensure the persistent agent exists (create-once / reuse-many)
      3. Send the processing request via Responses API
      4. Handle MCP approval flow if needed
      5. Return the parsed agent output

    The agent is NOT deleted after execution — it persists across requests
    and is visible in the Foundry portal.

    Returns:
        dict with agent response details
    """
    from azure.ai.projects import AIProjectClient

    # ── Initialize client ─────────────────────────────────────
    try:
        credential = DefaultAzureCredential()
    except Exception:
        credential = AzureCliCredential()

    project_client = AIProjectClient(
        endpoint=AI_PROJECT_ENDPOINT,
        credential=credential,
    )
    openai_client = project_client.get_openai_client()

    # ── Ensure agent exists (persistent) ──────────────────────
    agent = _ensure_agent_exists(project_client)

    # ── Get the latest version for the agent reference ────────
    agent_version = getattr(agent, "version", None)
    if not agent_version:
        try:
            versions = project_client.agents.list_versions(agent_name=agent.name)
            version_list = list(versions)
            if version_list:
                agent_version = version_list[-1].version
        except Exception as ver_err:
            logger.warning("Could not list agent versions: %s", ver_err)
            agent_version = "1"

    # ── Run the agent ─────────────────────────────────────────
    user_input = build_agent_input(ticket_id)
    logger.info("Sending request to agent %s v%s for ticket %s", agent.name, agent_version, ticket_id)

    with _tracer.start_as_current_span("stage-c-agent-call", attributes={"ticket.id": ticket_id, "agent.name": agent.name, "agent.version": str(agent_version)}):
        response = openai_client.responses.create(
            input=user_input,
            extra_body={
                "agent": {
                    "type": "agent_reference",
                    "name": agent.name,
                    "version": agent_version,
                },
            },
        )

        # Handle MCP approval requests and function calls
        response = _handle_tool_calls(openai_client, response, agent, agent_version)

    output_text = response.output_text if hasattr(response, "output_text") else ""
    logger.info(
        "Agent response received (status=%s, %d chars)",
        getattr(response, "status", "unknown"),
        len(output_text),
    )

    # Parse the response
    parsed = parse_agent_response(output_text)
    parsed["agent_id"] = agent.id
    parsed["agent_version"] = agent_version

    return parsed


def _handle_tool_calls(openai_client, response, agent, agent_version, max_rounds: int = 15) -> object:
    """
    Handle both MCP approval requests and function calls from the agent.

    With function tools defined in the agent, the agent emits function_call
    outputs for Payment API operations.  We execute them client-side and
    feed the results back.  MCP approval requests are auto-approved.
    """
    for round_num in range(max_rounds):
        tool_outputs = []

        for item in response.output:
            item_type = getattr(item, "type", "")

            # Handle MCP approval requests (auto-approve for demo)
            if item_type == "mcp_approval_request" and getattr(item, "id", None):
                from openai.types.responses.response_input_param import McpApprovalResponse

                tool_outputs.append(
                    McpApprovalResponse(
                        type="mcp_approval_response",
                        approve=True,
                        approval_request_id=item.id,
                    )
                )

            # Handle function calls (Payment API)
            elif item_type == "function_call":
                func_name = getattr(item, "name", "")
                call_id = getattr(item, "call_id", "")
                arguments_str = getattr(item, "arguments", "{}")

                logger.info("Function call: %s (call_id=%s)", func_name, call_id)
                try:
                    arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    result = _execute_payment_function(func_name, arguments)
                except Exception as e:
                    logger.error("Function execution error: %s — %s", func_name, e)
                    result = {"error": str(e)}

                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, default=str),
                })

        if not tool_outputs:
            return response  # No more tool calls to handle

        logger.info("Round %d: handling %d tool outputs", round_num + 1, len(tool_outputs))
        response = openai_client.responses.create(
            input=tool_outputs,
            previous_response_id=response.id,
            extra_body={
                "agent": {
                    "type": "agent_reference",
                    "name": agent.name,
                    "version": agent_version,
                },
            },
        )

    return response


def _execute_payment_function(func_name: str, arguments: dict) -> dict:
    """
    Execute a Payment API function call by making an HTTP request.

    Maps function tool calls to the Payment API HTTP endpoints.
    """
    import urllib.request
    import urllib.error

    base_url = PAYMENT_API_ENDPOINT.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if PAYMENT_API_KEY:
        headers["x-functions-key"] = PAYMENT_API_KEY

    if func_name == "validate_invoice":
        url = f"{base_url}/api/payments/validate"
        payload = json.dumps(arguments).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    elif func_name == "submit_payment":
        url = f"{base_url}/api/payments/submit"
        payload = json.dumps(arguments).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    elif func_name == "get_payment_status":
        payment_id = arguments.get("payment_id", "")
        url = f"{base_url}/api/payments/{payment_id}"
        req = urllib.request.Request(url, headers=headers, method="GET")

    else:
        return {"error": f"Unknown function: {func_name}"}

    try:
        logger.info("Calling Payment API: %s %s", req.method, url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        logger.error("Payment API HTTP %d: %s", e.code, error_body[:500])
        return {"error": f"Payment API returned HTTP {e.code}", "details": error_body[:300]}
    except Exception as e:
        logger.error("Payment API call failed: %s", e)
        return {"error": f"Payment API call failed: {str(e)}"}


# ═══════════════════════════════════════════════════════════════════
# HTTP Trigger: Process an invoice through Stage C
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="process-invoice",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def process_invoice(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/process-invoice — Trigger invoice processing for a specific ticket.

    Request body:
    {
        "ticketId": "ZAVA-2026-00001"
    }

    This endpoint:
      1. Validates the ticket exists and is in "ai_processed" status.
      2. Sets status to "invoice_processing".
      3. Runs the Foundry Agent V2 with MCP and Payment API tools.
      4. The agent validates the invoice, submits payment if valid,
         and writes results back to Cosmos DB.
      5. Returns the processing result.

    On error, sets the ticket status to "error" with error details
    and returns a 200 with the error in the response body.
    """
    start_time = time.perf_counter()

    # Parse request
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            mimetype="application/json",
            status_code=400,
        )

    ticket_id = body.get("ticketId", "")
    if not ticket_id:
        return func.HttpResponse(
            json.dumps({"error": "ticketId is required"}),
            mimetype="application/json",
            status_code=400,
        )

    logger.info("═══ Stage C: Invoice Processing started for %s ═══", ticket_id)

    # Validate ticket exists and is in correct status
    try:
        container = _get_tickets_container()
        ticket = container.read_item(item=ticket_id, partition_key=ticket_id)
    except exceptions.CosmosResourceNotFoundError:
        return func.HttpResponse(
            json.dumps({"error": f"Ticket '{ticket_id}' not found"}),
            mimetype="application/json",
            status_code=404,
        )

    current_status = ticket.get("status", "")
    if current_status not in ("ai_processed", "invoice_processing", "error"):
        return func.HttpResponse(
            json.dumps({
                "error": f"Ticket '{ticket_id}' is in status '{current_status}', "
                         f"expected 'ai_processed'. Cannot process invoice.",
                "ticketId": ticket_id,
                "currentStatus": current_status,
            }),
            mimetype="application/json",
            status_code=409,
        )

    # Set status → invoice_processing
    _update_ticket_status(ticket_id, {"status": "invoice_processing"})

    # Run the agent
    try:
        result = _create_and_run_agent(ticket_id)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if result.get("success"):
            logger.info(
                "═══ Stage C: Invoice Processing SUCCEEDED for %s (%.1f s) ═══",
                ticket_id, elapsed_ms / 1000,
            )

            # Clear stale error fields and persist processingTimeMs
            _update_ticket_status(ticket_id, {
                "invoiceProcessing": {
                    "errorMessage": None,
                    "errors": [],
                    "processingTimeMs": elapsed_ms,
                },
            })

            response_body = build_success_result(processing_time_ms=elapsed_ms)
            response_body["ticketId"] = ticket_id
            response_body["agentOutput"] = {
                "payment_submitted": result.get("payment_submitted", False),
                "payment_id": result.get("payment_id", ""),
                "validations": result.get("validations", {}),
                "errors": result.get("errors", []),
            }

            return func.HttpResponse(
                json.dumps(response_body, default=str),
                mimetype="application/json",
                status_code=200,
            )
        else:
            # Agent returned something but it didn't look like success
            error_msg = result.get("error", "Agent did not return expected output")
            logger.warning(
                "Stage C: Agent response unclear for %s: %s",
                ticket_id, error_msg,
            )

            # Write error state to Cosmos DB
            fallback = build_fallback_result(ticket_id, error_msg, elapsed_ms)
            _update_ticket_status(ticket_id, fallback)

            return func.HttpResponse(
                json.dumps({
                    "ticketId": ticket_id,
                    "status": "error",
                    "error": error_msg,
                    "rawOutput": result.get("raw_output", "")[:500],
                    "processingTimeMs": elapsed_ms,
                }),
                mimetype="application/json",
                status_code=200,
            )

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = f"Agent execution failed: {str(e)}"
        logger.error(
            "═══ Stage C: Invoice Processing FAILED for %s ═══\n%s",
            ticket_id, traceback.format_exc(),
        )

        # Write error state to Cosmos DB
        fallback = build_fallback_result(ticket_id, error_msg, elapsed_ms)
        _update_ticket_status(ticket_id, fallback)

        return func.HttpResponse(
            json.dumps({
                "ticketId": ticket_id,
                "status": "error",
                "error": error_msg,
                "processingTimeMs": elapsed_ms,
            }),
            mimetype="application/json",
            status_code=200,
        )
