"""
FastAPI application entry point for Zava Processing Inc. Ticket Processing System.

Configures:
  • CORS middleware for frontend access
  • Lifespan events for Cosmos DB and Blob Storage init/cleanup
  • API routers for tickets and dashboard
  • Health check endpoint
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import tickets, dashboard
from app.services import cosmos_client, blob_storage, storage

# ═══════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Lifespan — startup / shutdown
# ═══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    # ── Startup ──
    logger.info("Starting Zava Processing backend (env=%s)...", settings.app_env)

    # Initialize storage (Cosmos DB or in-memory fallback)
    if settings.cosmos_configured:
        try:
            storage.initialize()
            logger.info("✅ Cosmos DB initialized (endpoint=%s).", settings.cosmos_endpoint)
        except Exception as e:
            logger.error("❌ Cosmos DB initialization failed: %s", e)
            logger.warning("   Falling back to in-memory storage.")
            from app.services import memory_store
            memory_store.initialize()
    else:
        logger.warning(
            "⚠️  Cosmos DB not configured — using in-memory storage. "
            "(endpoint=%r, key=%s, managed_identity=%s)",
            settings.cosmos_endpoint[:30] + "..." if settings.cosmos_endpoint else "",
            "set" if settings.cosmos_key else "empty",
            settings.use_managed_identity,
        )
        from app.services import memory_store
        memory_store.initialize()

    # Initialize Blob Storage
    if settings.blob_configured:
        try:
            blob_storage.initialize_blob_storage()
            logger.info("✅ Blob Storage initialized.")
        except Exception as e:
            logger.error("❌ Blob Storage initialization failed: %s", e)
    else:
        logger.warning("⚠️  Blob Storage not configured.")

    logger.info("🚀 Zava Processing backend ready.")

    yield

    # ── Shutdown ──
    logger.info("Shutting down Zava Processing backend...")
    storage.close()
    blob_storage.close_blob_storage()
    logger.info("Shutdown complete.")


# ═══════════════════════════════════════════════════════════════════
# App Creation
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Zava Processing Inc. — Ticket Processing API",
    description=(
        "AI-powered ticket processing pipeline for automated invoice handling. "
        "Extracts data from PDFs, processes through Foundry V2 AI Agents, "
        "and automates invoice validation and payment submission."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════
# Middleware
# ═══════════════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════
# Routers
# ═══════════════════════════════════════════════════════════════════

app.include_router(tickets.router)
app.include_router(dashboard.router)


# ═══════════════════════════════════════════════════════════════════
# Static: Sample PDFs (for demo presets)
# ═══════════════════════════════════════════════════════════════════

# Try multiple locations for the sample PDFs directory
# 1. Inside the backend package (Docker): /app/data/sample_pdfs
# 2. Repo root (local dev): ../../data/sample_pdfs
_app_root = Path(__file__).resolve().parent.parent  # /app or backend/
_sample_pdfs_dir = _app_root / "data" / "sample_pdfs"
if not _sample_pdfs_dir.is_dir():
    _sample_pdfs_dir = _app_root.parent / "data" / "sample_pdfs"
if _sample_pdfs_dir.is_dir():
    app.mount(
        "/data",
        StaticFiles(directory=str(_sample_pdfs_dir)),
        name="sample_pdfs",
    )


# ═══════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════

@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint for container orchestrators and load balancers.
    Returns the application status and configuration summary.
    """
    cosmos_ok = settings.cosmos_configured
    blob_ok = settings.blob_configured

    return {
        "status": "healthy",
        "service": "zava-ticket-processing-api",
        "version": "0.1.0",
        "environment": settings.app_env,
        "dependencies": {
            "cosmos_db": "configured" if cosmos_ok else "not_configured",
            "blob_storage": "configured" if blob_ok else "not_configured",
        },
    }


@app.get("/debug/config", tags=["debug"])
async def debug_config():
    """Diagnostic endpoint for Content Understanding config (temporary)."""
    import os
    return {
        "content_understanding_configured": settings.content_understanding_configured,
        "content_understanding_endpoint": bool(settings.content_understanding_endpoint),
        "content_understanding_key_set": bool(settings.content_understanding_key),
        "use_managed_identity": settings.use_managed_identity,
    }


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API info."""
    return {
        "service": "Zava Processing Inc. — Ticket Processing API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
