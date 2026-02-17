"""
Dashboard API endpoints.

Provides aggregated metrics for Tab 5 (Overall Dashboard) in the UI.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.ticket import DashboardMetrics
from app.services import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics():
    """
    Get aggregated pipeline metrics for the dashboard.

    Returns:
      - Total ticket count and breakdown by status
      - Average processing times per stage
      - Success rate
      - Payment and manual review counts
    """
    try:
        metrics = storage.compute_dashboard_metrics()
        return metrics
    except Exception as e:
        logger.error("Failed to compute dashboard metrics: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute metrics: {e}",
        )
