"""
Stage B — AI Information Processing Agent (Azure Function)

Processes tickets that have been through extraction (status == "extracted")
by running a Foundry Agent V2 that standardizes codes, creates summaries,
and assigns next actions.

Triggers:
  HTTP POST /api/process-ticket  — Trigger processing for a specific ticket
    Body: {"ticketId": "ZAVA-2026-00001"}

In production this would be a Cosmos DB Change Feed trigger that fires
automatically when a ticket reaches "extracted" status. For the demo we
use an HTTP trigger so the UI can control timing.

The agent uses MCP tools (Cosmos DB) and has code mapping data
embedded directly in its instructions for code standardization.

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

from agent_logic import (
    AGENT_NAME,
    AGENT_INSTRUCTIONS,
    build_instructions_with_code_mappings,
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
    logger.info("OpenTelemetry tracer initialized for Stage B")
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
# Code mappings loader (embedded in agent instructions)
# ═══════════════════════════════════════════════════════════════════

_code_mappings_str = None


def _load_code_mappings() -> str:
    """Load the code mappings JSON for embedding in agent instructions."""
    global _code_mappings_str
    if _code_mappings_str is not None:
        return _code_mappings_str

    mappings_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "code_mappings.json",
    )

    try:
        with open(mappings_path, "r", encoding="utf-8") as f:
            _code_mappings_str = f.read()
        logger.info("Loaded code mappings from %s (%d chars)", mappings_path, len(_code_mappings_str))
        return _code_mappings_str
    except FileNotFoundError:
        logger.error("Code mappings not found at %s", mappings_path)
        return "{}"


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

    # Load code mappings and embed in agent instructions
    code_mappings_json = _load_code_mappings()
    enhanced_instructions = build_instructions_with_code_mappings(code_mappings_json)

    definition = PromptAgentDefinition(
        model=MODEL_DEPLOYMENT_NAME,
        instructions=enhanced_instructions,
        tools=[mcp_tool],
    )

    # ── Create or retrieve the persistent agent ───────
    try:
        logger.info("Creating persistent Foundry Agent V2: %s", AGENT_NAME)
        agent = project_client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=definition,
            description="AI Information Processing Agent for Zava Processing ticket pipeline",
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
    Run the persistent Foundry Agent V2 against a ticket.

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

    with _tracer.start_as_current_span("stage-b-agent-call", attributes={"ticket.id": ticket_id, "agent.name": agent.name, "agent.version": str(agent_version)}):
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

        # Handle MCP approval requests if any
        response = _handle_mcp_approvals(openai_client, response, agent, agent_version)

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


def _handle_mcp_approvals(openai_client, response, agent, agent_version, max_rounds: int = 5) -> object:
    """
    Handle MCP approval requests from the agent.

    When require_approval is not "never", the agent may send
    mcp_approval_request items that we need to approve and send back.
    We auto-approve all MCP tool calls for the demo.
    """
    for _ in range(max_rounds):
        approval_inputs = []

        for item in response.output:
            if getattr(item, "type", "") == "mcp_approval_request" and getattr(item, "id", None):
                from openai.types.responses.response_input_param import McpApprovalResponse

                approval_inputs.append(
                    McpApprovalResponse(
                        type="mcp_approval_response",
                        approve=True,
                        approval_request_id=item.id,
                    )
                )

        if not approval_inputs:
            return response  # No approvals needed

        logger.info("Auto-approving %d MCP requests", len(approval_inputs))
        response = openai_client.responses.create(
            input=approval_inputs,
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


# ═══════════════════════════════════════════════════════════════════
# HTTP Trigger: Process a ticket through Stage B
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="process-ticket",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def process_ticket(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/process-ticket — Trigger AI processing for a specific ticket.

    Request body:
    {
        "ticketId": "ZAVA-2026-00001"
    }

    This endpoint:
      1. Validates the ticket exists and is in "extracted" status.
      2. Sets status to "ai_processing".
      3. Runs the Foundry Agent V2 with MCP tools and embedded code mappings.
      4. The agent reads the ticket, standardizes codes, creates a summary,
         assigns a next action, and writes results back to Cosmos DB.
      5. Returns the processing result.

    On error, sets the ticket status to "ai_processing" with error details
    and returns a 200 with the error in the response body (not a 5xx,
    because the function itself succeeded — it's the agent that failed).
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

    logger.info("═══ Stage B: AI Processing started for %s ═══", ticket_id)

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
    if current_status not in ("extracted", "ai_processing", "error"):
        return func.HttpResponse(
            json.dumps({
                "error": f"Ticket '{ticket_id}' is in status '{current_status}', "
                         f"expected 'extracted'. Cannot process.",
                "ticketId": ticket_id,
                "currentStatus": current_status,
            }),
            mimetype="application/json",
            status_code=409,
        )

    # Set status → ai_processing
    _update_ticket_status(ticket_id, {"status": "ai_processing"})

    # Run the agent
    try:
        result = _create_and_run_agent(ticket_id)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if result.get("success"):
            logger.info(
                "═══ Stage B: AI Processing SUCCEEDED for %s (%.1f s) ═══",
                ticket_id, elapsed_ms / 1000,
            )

            # Clear stale error fields and persist processingTimeMs
            _update_ticket_status(ticket_id, {
                "aiProcessing": {
                    "errorMessage": None,
                    "processingTimeMs": elapsed_ms,
                },
            })

            response_body = build_success_result(processing_time_ms=elapsed_ms)
            response_body["ticketId"] = ticket_id
            response_body["agentOutput"] = {
                "summary": result.get("summary", ""),
                "next_action": result.get("next_action", ""),
                "standardized_codes": result.get("standardized_codes", {}),
                "flags": result.get("flags", []),
            }

            return func.HttpResponse(
                json.dumps(response_body, default=str),
                mimetype="application/json",
                status_code=200,
            )
        else:
            # Agent returned something but it didn't look like success
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            error_msg = result.get("error", "Agent did not return expected output")
            logger.warning(
                "Stage B: Agent response unclear for %s: %s",
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
            "═══ Stage B: AI Processing FAILED for %s ═══\n%s",
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
