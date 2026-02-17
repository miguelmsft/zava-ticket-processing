"""
Tests for the Dashboard API endpoint (app.routers.dashboard).

Covers:
  • GET /api/dashboard/metrics — success
  • GET /api/dashboard/metrics — Cosmos failure → 500
"""

from unittest.mock import patch

import pytest

from app.models.ticket import DashboardMetrics


class TestDashboardMetrics:
    def test_returns_metrics(self, test_client):
        mock_metrics = DashboardMetrics(
            total_tickets=25,
            tickets_by_status={"ingested": 5, "extracted": 5, "invoice_processed": 10, "error": 5},
            avg_extraction_time_ms=800.0,
            avg_ai_processing_time_ms=3500.0,
            avg_invoice_processing_time_ms=2200.0,
            avg_total_pipeline_time_ms=6500.0,
            success_rate=0.67,
            tickets_processed_today=3,
            payment_submitted_count=8,
            manual_review_count=2,
            error_count=5,
        )
        with patch("app.routers.dashboard.storage") as mock_cosmos:
            mock_cosmos.compute_dashboard_metrics.return_value = mock_metrics
            resp = test_client.get("/api/dashboard/metrics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_tickets"] == 25
        assert body["success_rate"] == 0.67
        assert body["payment_submitted_count"] == 8
        assert "tickets_by_status" in body

    def test_cosmos_failure(self, test_client):
        with patch("app.routers.dashboard.storage") as mock_cosmos:
            mock_cosmos.compute_dashboard_metrics.side_effect = Exception("DB down")
            resp = test_client.get("/api/dashboard/metrics")

        assert resp.status_code == 500
        assert "Failed to compute metrics" in resp.json()["detail"]

    def test_empty_metrics(self, test_client):
        """Dashboard with zero tickets should return valid defaults."""
        mock_metrics = DashboardMetrics()
        with patch("app.routers.dashboard.storage") as mock_cosmos:
            mock_cosmos.compute_dashboard_metrics.return_value = mock_metrics
            resp = test_client.get("/api/dashboard/metrics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_tickets"] == 0
        assert body["success_rate"] == 0.0
