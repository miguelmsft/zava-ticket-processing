"""
In-memory storage backend for development mode.

When Cosmos DB is not configured, this module provides a dict-based
store that implements the same interface as cosmos_client.py functions.
This lets the full UI pipeline work locally without any external services.
"""

from __future__ import annotations

import copy
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.models.ticket import (
    DashboardMetrics,
    TicketListResponse,
    TicketStatus,
    TicketSummary,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# In-Memory Stores
# ═══════════════════════════════════════════════════════════════════

_tickets: dict[str, dict] = {}
_code_mappings: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════
# Initialization / Cleanup
# ═══════════════════════════════════════════════════════════════════

def initialize() -> None:
    """No-op init for in-memory store."""
    logger.info("In-memory storage initialized (development mode).")


def close() -> None:
    """Clear in-memory storage."""
    global _tickets, _code_mappings
    _tickets.clear()
    _code_mappings.clear()
    logger.info("In-memory storage cleared.")


# ═══════════════════════════════════════════════════════════════════
# Ticket CRUD
# ═══════════════════════════════════════════════════════════════════

def create_ticket(doc: dict) -> dict:
    """Store a ticket in the in-memory dict."""
    ticket_id = doc.get("ticketId") or doc.get("id")
    if not ticket_id:
        raise ValueError("Document must have 'ticketId'")

    stored = copy.deepcopy(doc)
    stored.setdefault("id", ticket_id)
    stored.setdefault("ticketId", ticket_id)
    stored.setdefault("createdAt", _now_iso())
    stored.setdefault("updatedAt", _now_iso())

    _tickets[ticket_id] = stored
    logger.info("In-memory: created ticket %s (total: %d)", ticket_id, len(_tickets))
    return copy.deepcopy(stored)


def get_ticket(ticket_id: str) -> Optional[dict]:
    """Point read from in-memory dict."""
    doc = _tickets.get(ticket_id)
    return copy.deepcopy(doc) if doc else None


def update_ticket(ticket_id: str, updates: dict) -> Optional[dict]:
    """Read-modify-write in memory."""
    current = _tickets.get(ticket_id)
    if current is None:
        logger.warning("In-memory: ticket %s not found for update.", ticket_id)
        return None

    def _deep_merge(base: dict, overlay: dict) -> dict:
        for k, v in overlay.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                _deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    _deep_merge(current, updates)
    current["updatedAt"] = _now_iso()
    _tickets[ticket_id] = current
    logger.info("In-memory: updated ticket %s", ticket_id)
    return copy.deepcopy(current)


def list_tickets(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> TicketListResponse:
    """List tickets with in-memory filtering and pagination."""
    all_docs = sorted(
        _tickets.values(),
        key=lambda d: d.get("createdAt", ""),
        reverse=True,
    )

    if status_filter:
        all_docs = [d for d in all_docs if d.get("status") == status_filter]

    total_count = len(all_docs)
    offset = (page - 1) * page_size
    page_docs = all_docs[offset : offset + page_size]

    summaries = []
    for item in page_docs:
        raw = item.get("raw") or {}
        extraction = item.get("extraction") or {}
        ai = item.get("aiProcessing") or {}
        inv = item.get("invoiceProcessing") or {}

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
    """Delete a ticket from the in-memory dict."""
    if ticket_id in _tickets:
        del _tickets[ticket_id]
        logger.info("In-memory: deleted ticket %s", ticket_id)
        return True
    return False


# ═══════════════════════════════════════════════════════════════════
# Code Mappings
# ═══════════════════════════════════════════════════════════════════

def get_code_mappings(mapping_type: Optional[str] = None) -> list[dict]:
    """Retrieve code mappings from in-memory store."""
    if mapping_type:
        doc = _code_mappings.get(mapping_type)
        return [copy.deepcopy(doc)] if doc else []
    return [copy.deepcopy(d) for d in _code_mappings.values()]


# ═══════════════════════════════════════════════════════════════════
# Dashboard Metrics
# ═══════════════════════════════════════════════════════════════════

def compute_dashboard_metrics() -> DashboardMetrics:
    """Compute dashboard metrics from in-memory data."""
    from datetime import datetime, timezone
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    tickets_by_status: dict[str, int] = {}
    ext_times: list[float] = []
    ai_times: list[float] = []
    inv_times: list[float] = []
    payment_count = 0
    review_count = 0
    processed_today = 0

    for doc in _tickets.values():
        status = doc.get("status", "ingested")
        tickets_by_status[status] = tickets_by_status.get(status, 0) + 1

        created_at = doc.get("created_at", "")
        if isinstance(created_at, str) and created_at.startswith(today_prefix):
            processed_today += 1

        extraction = doc.get("extraction") or {}
        ai = doc.get("aiProcessing") or {}
        inv = doc.get("invoiceProcessing") or {}

        if extraction.get("processingTimeMs"):
            ext_times.append(extraction["processingTimeMs"])
        if ai.get("processingTimeMs"):
            ai_times.append(ai["processingTimeMs"])
        if inv.get("processingTimeMs"):
            inv_times.append(inv["processingTimeMs"])

        if (inv.get("paymentSubmission") or {}).get("submitted"):
            payment_count += 1
        if ai.get("nextAction") == "manual_review":
            review_count += 1

    total = sum(tickets_by_status.values())
    completed = tickets_by_status.get("invoice_processed", 0)
    errors = tickets_by_status.get("error", 0)
    success_rate = completed / (completed + errors) if (completed + errors) > 0 else 0.0

    avg_ext = sum(ext_times) / len(ext_times) if ext_times else 0
    avg_ai = sum(ai_times) / len(ai_times) if ai_times else 0
    avg_inv = sum(inv_times) / len(inv_times) if inv_times else 0

    return DashboardMetrics(
        total_tickets=total,
        tickets_by_status=tickets_by_status,
        avg_extraction_time_ms=avg_ext,
        avg_ai_processing_time_ms=avg_ai,
        avg_invoice_processing_time_ms=avg_inv,
        avg_total_pipeline_time_ms=avg_ext + avg_ai + avg_inv,
        success_rate=success_rate,
        tickets_processed_today=processed_today,
        payment_submitted_count=payment_count,
        manual_review_count=review_count,
        error_count=errors,
    )
