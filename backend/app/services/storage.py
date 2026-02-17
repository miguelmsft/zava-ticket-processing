"""
Storage abstraction — delegates to Cosmos DB or in-memory store.

When Cosmos DB is configured (endpoint + key set), all calls go to the
real ``cosmos_client`` module.  Otherwise, the lightweight ``memory_store``
is used, allowing the full UI pipeline to work locally without any
external services.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import get_settings
from app.models.ticket import DashboardMetrics, TicketListResponse

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Backend selection
# ═══════════════════════════════════════════════════════════════════

def _use_cosmos() -> bool:
    """Return True if Cosmos DB is configured (key or Managed Identity)."""
    s = get_settings()
    return s.cosmos_configured


# ── Initialisation / shutdown (called by main.py lifespan) ────────

def initialize() -> None:
    if _use_cosmos():
        from app.services import cosmos_client
        cosmos_client.initialize_cosmos()
    else:
        from app.services import memory_store
        memory_store.initialize()


def close() -> None:
    if _use_cosmos():
        from app.services import cosmos_client
        cosmos_client.close_cosmos()
    else:
        from app.services import memory_store
        memory_store.close()


# ── Ticket CRUD ───────────────────────────────────────────────────

def create_ticket(doc: dict) -> dict:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.create_ticket(doc)
    from app.services import memory_store
    return memory_store.create_ticket(doc)


def get_ticket(ticket_id: str) -> Optional[dict]:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.get_ticket(ticket_id)
    from app.services import memory_store
    return memory_store.get_ticket(ticket_id)


def update_ticket(ticket_id: str, updates: dict) -> Optional[dict]:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.update_ticket(ticket_id, updates)
    from app.services import memory_store
    return memory_store.update_ticket(ticket_id, updates)


def list_tickets(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> TicketListResponse:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.list_tickets(page, page_size, status_filter)
    from app.services import memory_store
    return memory_store.list_tickets(page, page_size, status_filter)


def delete_ticket(ticket_id: str) -> bool:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.delete_ticket(ticket_id)
    from app.services import memory_store
    return memory_store.delete_ticket(ticket_id)


# ── Code Mappings ─────────────────────────────────────────────────

def get_code_mappings(mapping_type: Optional[str] = None) -> list[dict]:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.get_code_mappings(mapping_type)
    from app.services import memory_store
    return memory_store.get_code_mappings(mapping_type)


# ── Dashboard ─────────────────────────────────────────────────────

def compute_dashboard_metrics() -> DashboardMetrics:
    if _use_cosmos():
        from app.services import cosmos_client
        return cosmos_client.compute_dashboard_metrics()
    from app.services import memory_store
    return memory_store.compute_dashboard_metrics()
