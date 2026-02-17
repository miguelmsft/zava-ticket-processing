"""
Cosmos DB MCP Server — Azure Function

Exposes Cosmos DB ticket operations as MCP (Model Context Protocol) tools
that Foundry Agent V2 can call via APIM AI Gateway.

Tools:
  • read_ticket      — Read a single ticket by ticketId (point read).
  • update_ticket     — Update specific fields on a ticket document.
  • query_tickets_by_status — Query tickets filtered by pipeline status.

Reference:
  - Azure-Samples/remote-mcp-functions-python
  - https://learn.microsoft.com/azure/azure-functions/scenario-custom-remote-mcp-server
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import azure.functions as func
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

from cosmos_helpers import (
    clean_doc as _clean_doc,
    deep_merge as _deep_merge,
    ToolProperty,
    parse_mcp_context,
    READ_TICKET_PROPS as read_ticket_props,
    UPDATE_TICKET_PROPS as update_ticket_props,
    QUERY_STATUS_PROPS as query_status_props,
)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Cosmos DB Singleton
# ═══════════════════════════════════════════════════════════════════

_cosmos_client: Optional[CosmosClient] = None
_database = None

COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_KEY = os.environ.get("COSMOS_KEY", "")
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "zava-ticket-processing")
COSMOS_USE_EMULATOR = os.environ.get("COSMOS_USE_EMULATOR", "false").lower() == "true"

TICKETS_CONTAINER = "tickets"


def _get_cosmos_client() -> CosmosClient:
    """Return singleton CosmosClient."""
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
        logger.info("Cosmos DB MCP client created for %s", COSMOS_ENDPOINT)
    return _cosmos_client


def _get_tickets_container():
    """Return the tickets container proxy."""
    global _database
    if _database is None:
        _database = _get_cosmos_client().get_database_client(COSMOS_DATABASE)
    return _database.get_container_client(TICKETS_CONTAINER)


# ═══════════════════════════════════════════════════════════════════
# MCP Tool: read_ticket
# ═══════════════════════════════════════════════════════════════════

@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="read_ticket",
    description=(
        "Read a single ticket document from Cosmos DB by its ticketId. "
        "Returns the full ticket document including ingestion data, "
        "extraction results, AI processing results, and invoice processing results."
    ),
    toolProperties=read_ticket_props,
)
def read_ticket(context) -> str:
    """MCP tool: Read a ticket by ticketId (point read with partition key)."""
    args = parse_mcp_context(context)
    ticket_id = args.get("ticket_id", "")

    if not ticket_id:
        return json.dumps({"error": "ticket_id is required"})

    container = _get_tickets_container()
    start = time.perf_counter()

    try:
        doc = container.read_item(item=ticket_id, partition_key=ticket_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("MCP read_ticket %s (%.1f ms)", ticket_id, elapsed_ms)
        return json.dumps(_clean_doc(doc), default=str)
    except exceptions.CosmosResourceNotFoundError:
        return json.dumps({"error": f"Ticket '{ticket_id}' not found"})
    except exceptions.CosmosHttpResponseError as e:
        logger.error("Cosmos error in read_ticket: %s %s", e.status_code, e.message)
        return json.dumps({"error": f"Database error: {e.message}"})


# ═══════════════════════════════════════════════════════════════════
# MCP Tool: update_ticket
# ═══════════════════════════════════════════════════════════════════

@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="update_ticket",
    description=(
        "Update specific fields on a ticket document in Cosmos DB. "
        "Performs a read-modify-write with the provided field updates. "
        "The updates_json should be a valid JSON string of fields to merge. "
        "Automatically sets the 'updatedAt' timestamp."
    ),
    toolProperties=update_ticket_props,
)
def update_ticket(context) -> str:
    """MCP tool: Update a ticket with partial field updates."""
    args = parse_mcp_context(context)
    ticket_id = args.get("ticket_id", "")
    updates_json = args.get("updates_json", "{}")

    if not ticket_id:
        return json.dumps({"error": "ticket_id is required"})

    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid updates_json: {e}"})

    container = _get_tickets_container()

    # Point read → merge → upsert
    try:
        current = container.read_item(item=ticket_id, partition_key=ticket_id)
    except exceptions.CosmosResourceNotFoundError:
        return json.dumps({"error": f"Ticket '{ticket_id}' not found"})

    # Recursive deep merge — safely merges nested dicts without data loss
    _deep_merge(current, updates)

    current["updatedAt"] = datetime.now(timezone.utc).isoformat()

    start = time.perf_counter()
    try:
        result = container.upsert_item(body=current)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("MCP update_ticket %s (%.1f ms)", ticket_id, elapsed_ms)
        return json.dumps({
            "success": True,
            "ticketId": ticket_id,
            "updatedAt": current["updatedAt"],
            "updatedFields": list(updates.keys()),
        })
    except exceptions.CosmosHttpResponseError as e:
        logger.error("Cosmos error in update_ticket: %s %s", e.status_code, e.message)
        return json.dumps({"error": f"Database error: {e.message}"})


# ═══════════════════════════════════════════════════════════════════
# MCP Tool: query_tickets_by_status
# ═══════════════════════════════════════════════════════════════════

@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="query_tickets_by_status",
    description=(
        "Query tickets from Cosmos DB filtered by their pipeline status. "
        "Returns a list of ticket summaries (ticketId, status, title, "
        "createdAt, updatedAt). Use 'max_results' to limit the number of results."
    ),
    toolProperties=query_status_props,
)
def query_tickets_by_status(context) -> str:
    """MCP tool: Query tickets by pipeline status."""
    args = parse_mcp_context(context)
    status = args.get("status", "")
    max_results_str = args.get("max_results", "10")

    if not status:
        return json.dumps({"error": "status is required"})

    try:
        max_results = int(max_results_str)
    except ValueError:
        max_results = 10

    max_results = min(max_results, 50)  # Cap at 50

    container = _get_tickets_container()
    start = time.perf_counter()

    try:
        query = (
            "SELECT c.id, c.ticketId, c.status, c.createdAt, c.updatedAt, "
            "c.ingestion.title AS title "
            "FROM c WHERE c.status = @status "
            "ORDER BY c.createdAt DESC "
            "OFFSET 0 LIMIT @limit"
        )
        params = [
            {"name": "@status", "value": status},
            {"name": "@limit", "value": max_results},
        ]

        items = list(container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        ))

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "MCP query_tickets_by_status status=%s count=%d (%.1f ms)",
            status, len(items), elapsed_ms,
        )

        return json.dumps({
            "status": status,
            "count": len(items),
            "tickets": items,
        }, default=str)

    except exceptions.CosmosHttpResponseError as e:
        logger.error(
            "Cosmos error in query_tickets_by_status: %s %s",
            e.status_code, e.message,
        )
        return json.dumps({"error": f"Database error: {e.message}"})
