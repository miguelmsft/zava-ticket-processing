"""
Azure Cosmos DB service layer for the Zava Processing pipeline.

Best practices applied:
  • Singleton CosmosClient — reused across the application lifetime.
  • Async not available in azure-cosmos sync SDK; we wrap sync calls.
    (The azure.cosmos.aio async client is used when the package supports it.)
  • Retry-after logic for 429 (Request Rate Too Large) via SDK defaults.
  • Diagnostic logging for high-latency or unexpected status codes.
  • Partition key (/ticketId) used in all point reads/writes for efficiency.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.cosmos.container import ContainerProxy
from azure.cosmos.database import DatabaseProxy

from app.config import get_settings
from app.models.ticket import (
    DashboardMetrics,
    TicketListResponse,
    TicketStatus,
    TicketSummary,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Singleton Client
# ═══════════════════════════════════════════════════════════════════

_client: Optional[CosmosClient] = None
_database: Optional[DatabaseProxy] = None

# Container names
TICKETS_CONTAINER = "tickets"
CODE_MAPPINGS_CONTAINER = "code-mappings"
METRICS_CONTAINER = "metrics"


def get_cosmos_client() -> CosmosClient:
    """Return the singleton CosmosClient, creating it if needed.

    Supports two authentication modes:
      1. Key-based auth (cosmos_key is set)
      2. Managed Identity auth (azure_client_id is set, cosmos_key empty)
    """
    global _client
    if _client is None:
        settings = get_settings()
        kwargs = {}
        if settings.cosmos_use_emulator:
            kwargs["connection_verify"] = False

        if settings.cosmos_key:
            # Key-based authentication
            credential = settings.cosmos_key
            logger.info("Cosmos DB client using key-based auth for %s", settings.cosmos_endpoint)
        else:
            # Managed Identity authentication
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
            if settings.azure_client_id:
                credential = ManagedIdentityCredential(client_id=settings.azure_client_id)
                logger.info(
                    "Cosmos DB client using Managed Identity (client_id=%s) for %s",
                    settings.azure_client_id[:8] + "...",
                    settings.cosmos_endpoint,
                )
            else:
                credential = DefaultAzureCredential()
                logger.info("Cosmos DB client using DefaultAzureCredential for %s", settings.cosmos_endpoint)

        _client = CosmosClient(
            url=settings.cosmos_endpoint,
            credential=credential,
            **kwargs,
        )
        logger.info("Cosmos DB client created successfully.")
    return _client


def get_database() -> DatabaseProxy:
    """Return the singleton database reference, creating it if needed."""
    global _database
    if _database is None:
        settings = get_settings()
        client = get_cosmos_client()
        _database = client.get_database_client(settings.cosmos_database)
        logger.info("Cosmos DB database reference: %s", settings.cosmos_database)
    return _database


def get_tickets_container() -> ContainerProxy:
    """Return the tickets container client."""
    return get_database().get_container_client(TICKETS_CONTAINER)


def get_code_mappings_container() -> ContainerProxy:
    """Return the code-mappings container client."""
    return get_database().get_container_client(CODE_MAPPINGS_CONTAINER)


def get_metrics_container() -> ContainerProxy:
    """Return the metrics container client."""
    return get_database().get_container_client(METRICS_CONTAINER)


# ═══════════════════════════════════════════════════════════════════
# Initialization (called at app startup)
# ═══════════════════════════════════════════════════════════════════

def initialize_cosmos() -> None:
    """
    Ensure the database and containers exist.
    Called once during FastAPI lifespan startup.
    """
    settings = get_settings()
    client = get_cosmos_client()

    logger.info("Ensuring Cosmos DB database '%s' exists...", settings.cosmos_database)
    database = client.create_database_if_not_exists(id=settings.cosmos_database)

    containers = [
        (TICKETS_CONTAINER, "/ticketId"),
        (CODE_MAPPINGS_CONTAINER, "/mappingType"),
        (METRICS_CONTAINER, "/metricType"),
    ]

    for container_name, pk_path in containers:
        logger.info("  Ensuring container '%s' (PK: %s)...", container_name, pk_path)
        database.create_container_if_not_exists(
            id=container_name,
            partition_key=PartitionKey(path=pk_path),
        )

    # Cache the database reference
    global _database
    _database = database
    logger.info("Cosmos DB initialization complete.")


def close_cosmos() -> None:
    """Close the Cosmos DB client. Called during FastAPI lifespan shutdown."""
    global _client, _database
    if _client:
        _client.close()
        _client = None
        _database = None
        logger.info("Cosmos DB client closed.")


# ═══════════════════════════════════════════════════════════════════
# Ticket CRUD Operations
# ═══════════════════════════════════════════════════════════════════

def create_ticket(doc: dict) -> dict:
    """
    Create a new ticket document in Cosmos DB.

    Args:
        doc: Full ticket document dict (with 'id' and 'ticketId' set).

    Returns:
        The created document (with Cosmos metadata).
    """
    container = get_tickets_container()
    start = time.perf_counter()
    try:
        result = container.create_item(body=doc)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Created ticket %s (%.1f ms)",
            doc.get("ticketId"),
            elapsed_ms,
        )
        return result
    except exceptions.CosmosResourceExistsError:
        logger.warning("Ticket %s already exists, using upsert.", doc.get("ticketId"))
        return container.upsert_item(body=doc)
    except exceptions.CosmosHttpResponseError as e:
        logger.error(
            "Cosmos DB error creating ticket %s: status=%s, message=%s",
            doc.get("ticketId"), e.status_code, e.message,
        )
        raise


def get_ticket(ticket_id: str) -> Optional[dict]:
    """
    Read a single ticket by ticketId (point read with partition key).

    Args:
        ticket_id: The ticket ID (also the partition key).

    Returns:
        The ticket document dict, or None if not found.
    """
    container = get_tickets_container()
    start = time.perf_counter()
    try:
        result = container.read_item(item=ticket_id, partition_key=ticket_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 100:
            logger.warning(
                "Slow point read for ticket %s: %.1f ms", ticket_id, elapsed_ms,
            )
        return result
    except exceptions.CosmosResourceNotFoundError:
        return None
    except exceptions.CosmosHttpResponseError as e:
        logger.error(
            "Cosmos DB error reading ticket %s: status=%s, message=%s",
            ticket_id, e.status_code, e.message,
        )
        raise


def update_ticket(ticket_id: str, updates: dict) -> Optional[dict]:
    """
    Update specific fields on a ticket document.

    Reads the current document, merges updates, and upserts.
    Uses partition key for efficient point operations.

    Args:
        ticket_id: The ticket ID.
        updates: Dict of fields to merge into the document.

    Returns:
        The updated document, or None if the ticket was not found.
    """
    container = get_tickets_container()

    # Point read current state
    try:
        current = container.read_item(item=ticket_id, partition_key=ticket_id)
    except exceptions.CosmosResourceNotFoundError:
        logger.warning("Ticket %s not found for update.", ticket_id)
        return None

    # Merge updates
    current.update(updates)
    current["updatedAt"] = datetime.now(timezone.utc).isoformat()

    # Upsert back
    start = time.perf_counter()
    result = container.upsert_item(body=current)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("Updated ticket %s (%.1f ms)", ticket_id, elapsed_ms)
    return result


def list_tickets(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> TicketListResponse:
    """
    List tickets with pagination and optional status filter.

    Uses cross-partition query (acceptable for demo; in production use
    Change Feed or materialized views for list queries).
    """
    container = get_tickets_container()

    # Build query
    conditions = []
    params = []
    if status_filter:
        conditions.append("c.status = @status")
        params.append({"name": "@status", "value": status_filter})

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM c{where_clause} ORDER BY c.createdAt DESC"

    # Count query
    count_query = f"SELECT VALUE COUNT(1) FROM c{where_clause}"
    count_results = list(container.query_items(
        query=count_query,
        parameters=params or None,
        enable_cross_partition_query=True,
    ))
    total_count = count_results[0] if count_results else 0

    # Paginated data query
    offset = (page - 1) * page_size
    paged_query = f"{query} OFFSET {offset} LIMIT {page_size}"

    items = list(container.query_items(
        query=paged_query,
        parameters=params or None,
        enable_cross_partition_query=True,
    ))

    # Map to summaries
    summaries = []
    for item in items:
        raw = item.get("raw", {})
        extraction = item.get("extraction", {})
        ai = item.get("aiProcessing", {})
        inv = item.get("invoiceProcessing", {})

        summaries.append(TicketSummary(
            ticket_id=item.get("ticketId", ""),
            title=raw.get("title", item.get("ticketId", "")),
            status=item.get("status", "ingested"),
            priority=raw.get("priority", "normal"),
            submitter_name=raw.get("submitterName", ""),
            created_at=item.get("createdAt"),
            updated_at=item.get("updatedAt"),
            has_extraction=extraction.get("status") not in ("pending", None),
            has_ai_processing=ai.get("status") not in ("pending", None),
            has_invoice_processing=inv.get("status") not in ("pending", None),
        ))

    return TicketListResponse(
        tickets=summaries,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


def delete_ticket(ticket_id: str) -> bool:
    """Delete a ticket by ID. Returns True if deleted, False if not found."""
    container = get_tickets_container()
    try:
        container.delete_item(item=ticket_id, partition_key=ticket_id)
        logger.info("Deleted ticket %s", ticket_id)
        return True
    except exceptions.CosmosResourceNotFoundError:
        return False


# ═══════════════════════════════════════════════════════════════════
# Code Mappings Operations
# ═══════════════════════════════════════════════════════════════════

def get_code_mappings(mapping_type: Optional[str] = None) -> list[dict]:
    """
    Retrieve code mapping documents.

    Args:
        mapping_type: If provided, get a specific mapping type.
                      Otherwise, return all mappings.
    """
    container = get_code_mappings_container()

    if mapping_type:
        try:
            result = container.read_item(
                item=f"mapping-{mapping_type}",
                partition_key=mapping_type,
            )
            return [result]
        except exceptions.CosmosResourceNotFoundError:
            return []
    else:
        query = "SELECT * FROM c"
        return list(container.query_items(
            query=query,
            enable_cross_partition_query=True,
        ))


# ═══════════════════════════════════════════════════════════════════
# Dashboard Metrics
# ═══════════════════════════════════════════════════════════════════

def compute_dashboard_metrics() -> DashboardMetrics:
    """
    Compute real-time dashboard metrics by querying the tickets container.

    Uses simple cross-partition queries compatible with Cosmos DB serverless.
    Fetches lightweight projections and aggregates in Python.
    """
    container = get_tickets_container()

    # Fetch lightweight projection of all tickets
    projection_query = """
        SELECT
            c.status,
            c.createdAt,
            c.extraction.processingTimeMs AS extTime,
            c.aiProcessing.processingTimeMs AS aiTime,
            c.aiProcessing.nextAction AS nextAction,
            c.invoiceProcessing.processingTimeMs AS invTime,
            c.invoiceProcessing.paymentSubmission.submitted AS paymentSubmitted
        FROM c
    """
    items = list(container.query_items(
        query=projection_query,
        enable_cross_partition_query=True,
    ))

    total_tickets = len(items)

    # Today's date prefix for filtering (UTC)
    from datetime import datetime, timezone
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Status counts
    tickets_by_status: dict[str, int] = {}
    ext_times: list[float] = []
    ai_times: list[float] = []
    inv_times: list[float] = []
    payment_count = 0
    review_count = 0
    processed_today = 0

    for item in items:
        status = item.get("status", "unknown")
        tickets_by_status[status] = tickets_by_status.get(status, 0) + 1

        # Count tickets created today
        created_at = item.get("createdAt", "")
        if isinstance(created_at, str) and created_at.startswith(today_prefix):
            processed_today += 1

        if item.get("extTime"):
            ext_times.append(float(item["extTime"]))
        if item.get("aiTime"):
            ai_times.append(float(item["aiTime"]))
        if item.get("invTime"):
            inv_times.append(float(item["invTime"]))
        if item.get("paymentSubmitted"):
            payment_count += 1

        next_action = item.get("nextAction", "")
        if isinstance(next_action, str) and "manual_review" in next_action:
            review_count += 1

    avg_ext = sum(ext_times) / len(ext_times) if ext_times else 0
    avg_ai = sum(ai_times) / len(ai_times) if ai_times else 0
    avg_inv = sum(inv_times) / len(inv_times) if inv_times else 0

    completed_count = tickets_by_status.get("invoice_processed", 0)
    error_count = tickets_by_status.get("error", 0)
    success_rate = (
        completed_count / (completed_count + error_count)
        if (completed_count + error_count) > 0
        else 0.0
    )

    return DashboardMetrics(
        total_tickets=total_tickets,
        tickets_by_status=tickets_by_status,
        avg_extraction_time_ms=avg_ext,
        avg_ai_processing_time_ms=avg_ai,
        avg_invoice_processing_time_ms=avg_inv,
        avg_total_pipeline_time_ms=avg_ext + avg_ai + avg_inv,
        success_rate=success_rate,
        tickets_processed_today=processed_today,
        payment_submitted_count=payment_count,
        manual_review_count=review_count,
        error_count=error_count,
    )
