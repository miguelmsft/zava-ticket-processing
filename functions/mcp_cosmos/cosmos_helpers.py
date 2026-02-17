"""
Cosmos DB MCP Server — Pure Helper Utilities

Contains helper functions that can be imported without the Azure Functions SDK
or azure-cosmos SDK. Used by both function_app.py (runtime) and the test suite.
"""

import json


def clean_doc(doc: dict) -> dict:
    """Remove Cosmos DB internal fields (_rid, _self, _etag, _attachments, _ts)."""
    if doc is None:
        return {}
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def deep_merge(base: dict, updates: dict) -> dict:
    """
    Recursively merge *updates* into *base* (in-place).

    - If both base[key] and updates[key] are dicts → recurse.
    - Otherwise the value from *updates* wins.
    - Returns *base* for convenience.
    """
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class ToolProperty:
    """MCP tool property definition for Azure Functions mcpToolTrigger."""

    def __init__(self, property_name: str, property_type: str, description: str):
        self.propertyName = property_name
        self.propertyType = property_type
        self.description = description

    def to_dict(self) -> dict:
        return {
            "propertyName": self.propertyName,
            "propertyType": self.propertyType,
            "description": self.description,
        }


def parse_mcp_context(context_str: str) -> dict:
    """Parse the MCP tool context JSON string and return the arguments dict."""
    content = json.loads(context_str)
    return content.get("arguments", {})


# ── read_ticket properties ───────────────────────────────────────
READ_TICKET_PROPS = json.dumps([
    ToolProperty(
        "ticket_id", "string",
        "The unique ticket ID (e.g., 'ZAVA-2026-00001'). This is also the partition key."
    ).to_dict(),
])

# ── update_ticket properties ─────────────────────────────────────
UPDATE_TICKET_PROPS = json.dumps([
    ToolProperty(
        "ticket_id", "string",
        "The unique ticket ID to update (e.g., 'ZAVA-2026-00001')."
    ).to_dict(),
    ToolProperty(
        "updates_json", "string",
        "A JSON string containing the fields to update. "
        "Example: '{\"status\": \"ai_processed\", \"aiProcessing\": {\"summary\": \"...\"}}'"
    ).to_dict(),
])

# ── query_tickets_by_status properties ────────────────────────────
QUERY_STATUS_PROPS = json.dumps([
    ToolProperty(
        "status", "string",
        "The pipeline status to filter by. "
        "Valid values: 'submitted', 'extracting', 'extracted', "
        "'ai_processing', 'ai_processed', 'invoice_processing', "
        "'invoice_processed', 'completed', 'error'."
    ).to_dict(),
    ToolProperty(
        "max_results", "string",
        "Maximum number of tickets to return. Default is '10'. Must be a string representation of an integer."
    ).to_dict(),
])
