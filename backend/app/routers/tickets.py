"""
Ticket API endpoints.

Handles ticket ingestion (with PDF upload), listing, and per-stage
result retrieval. This is the primary router backing Tabs 1-4 in the UI.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile

from app.models.ticket import (
    Priority,
    TicketListResponse,
    TicketStatus,
)
from app.services import storage, blob_storage, extraction, ai_processing, invoice_processing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


# ═══════════════════════════════════════════════════════════════════
# POST /api/tickets — Ingest a new ticket
# ═══════════════════════════════════════════════════════════════════

@router.post("", status_code=201)
async def create_ticket(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    tags: str = Form(""),
    priority: Priority = Form(Priority.NORMAL),
    submitter: str = Form(""),
    submitter_name: str = Form(""),
    submitter_department: str = Form(""),
    extraction_method: str = Form("regex"),
    file: Optional[UploadFile] = File(None),
):
    """
    Submit a new ticket with an optional PDF attachment.

    This endpoint:
      1. Generates a unique ticket ID.
      2. Uploads the PDF to Azure Blob Storage (if provided).
      3. Creates the ticket document in Cosmos DB with status='ingested'.
      4. Triggers Stage A extraction in the background.
      5. Returns the created ticket immediately.
    """
    # Generate ticket ID
    ticket_number = str(uuid.uuid4().int)[:8].zfill(8)
    ticket_id = f"ZAVA-2026-{ticket_number}"
    now = datetime.now(timezone.utc).isoformat()

    # Parse tags from comma-separated string
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Handle file upload
    attachment = None
    file_bytes = None
    if file and file.filename:
        # Validate content type
        allowed_types = {"application/pdf", "application/octet-stream"}
        if file.content_type and file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '{file.content_type}'. Only PDF files are accepted.",
            )

        file_bytes = await file.read()

        # Validate file size (max 50 MB)
        max_size = 50 * 1024 * 1024
        if len(file_bytes) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({len(file_bytes)} bytes). Maximum is 50 MB.",
            )

        blob_result = blob_storage.upload_pdf(
            ticket_id=ticket_id,
            filename=file.filename,
            file_bytes=file_bytes,
        )
        attachment = {
            "filename": file.filename,
            "blobUrl": blob_result["blob_url"],
            "contentType": file.content_type or "application/pdf",
            "sizeBytes": blob_result["size_bytes"],
        }

    # Build Cosmos DB document
    doc = {
        "id": ticket_id,
        "ticketId": ticket_id,
        "status": TicketStatus.INGESTED.value,
        "createdAt": now,
        "updatedAt": now,

        "raw": {
            "title": title,
            "description": description,
            "tags": tag_list,
            "priority": priority.value,
            "submitter": submitter,
            "submitterName": submitter_name,
            "submitterDepartment": submitter_department,
            "extractionMethod": extraction_method,
        },

        "attachments": [attachment] if attachment else [],

        "extraction": {
            "status": "pending",
            "completedAt": None,
            "basicMetadata": None,
            "contentUnderstanding": None,
        },

        "aiProcessing": {
            "status": "pending",
            "completedAt": None,
            "standardizedCodes": None,
            "summary": None,
            "nextAction": None,
        },

        "invoiceProcessing": {
            "status": "pending",
            "completedAt": None,
            "validations": None,
            "paymentSubmission": None,
            "errors": [],
        },
    }

    # Persist to Cosmos DB
    try:
        result = storage.create_ticket(doc)
    except Exception as e:
        logger.error("Failed to create ticket: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create ticket: {e}")

    logger.info("Ticket %s created successfully.", ticket_id)

    # ── Stage A: Trigger extraction in background ────────────
    if file_bytes:
        blob_name = f"{ticket_id}/{file.filename}" if file and file.filename else None
        background_tasks.add_task(
            extraction.process_extraction,
            ticket_id=ticket_id,
            pdf_bytes=file_bytes,
            blob_name=blob_name,
            extraction_method=extraction_method,
        )
        logger.info("Extraction queued for ticket %s.", ticket_id)

    return {
        "ticketId": ticket_id,
        "status": "ingested",
        "message": f"Ticket {ticket_id} created successfully.",
        "attachment": attachment,
        "extractionQueued": bool(file_bytes),
    }


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets — List all tickets
# ═══════════════════════════════════════════════════════════════════

@router.get("", response_model=TicketListResponse)
async def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by pipeline status"),
):
    """
    List all tickets with pagination.

    Returns lightweight ticket summaries suitable for the ticket list UI.
    """
    try:
        return storage.list_tickets(
            page=page,
            page_size=page_size,
            status_filter=status,
        )
    except Exception as e:
        logger.error("Failed to list tickets: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to list tickets: {e}")


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets/{ticket_id} — Full ticket details
# ═══════════════════════════════════════════════════════════════════

@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str):
    """
    Get full ticket details (all pipeline stages).

    Returns the complete Cosmos DB document for the ticket.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    return doc


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets/{ticket_id}/extraction — Stage A results
# ═══════════════════════════════════════════════════════════════════

@router.get("/{ticket_id}/extraction")
async def get_extraction_results(ticket_id: str):
    """
    Get extraction results for a ticket (Stage A: Tab 2).

    Returns the raw ticket data + extraction output from Python
    libraries and Azure Content Understanding.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    return {
        "ticketId": ticket_id,
        "status": doc.get("status"),
        "raw": doc.get("raw"),
        "attachments": doc.get("attachments"),
        "extraction": doc.get("extraction"),
    }


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets/{ticket_id}/ai-processing — Stage B results
# ═══════════════════════════════════════════════════════════════════

@router.get("/{ticket_id}/ai-processing")
async def get_ai_processing_results(ticket_id: str):
    """
    Get AI processing results for a ticket (Stage B: Tab 3).

    Returns the standardized codes, summary, and next action
    produced by the Information Processing Agent.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    return {
        "ticketId": ticket_id,
        "status": doc.get("status"),
        "aiProcessing": doc.get("aiProcessing"),
    }


# ═══════════════════════════════════════════════════════════════════
# POST /api/tickets/{ticket_id}/process-ai — Trigger Stage B
# ═══════════════════════════════════════════════════════════════════

@router.post("/{ticket_id}/process-ai")
async def trigger_ai_processing(ticket_id: str, background_tasks: BackgroundTasks):
    """
    Trigger Stage B (AI Information Processing) for a ticket.

    The ticket must be in 'extracted' status. This endpoint:
      1. Validates the ticket status.
      2. Queues the AI processing as a background task.
      3. Returns immediately with a queued confirmation.

    The background task calls the Stage B Azure Function which runs
    the Foundry Agent V2 to standardize codes, create a summary,
    and assign the next action.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    current_status = doc.get("status", "")
    if current_status not in ("extracted", "ai_processing", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Ticket is in status '{current_status}', must be 'extracted' to trigger AI processing.",
        )

    # Queue the processing as a background task
    background_tasks.add_task(ai_processing.trigger_ai_processing, ticket_id)
    logger.info("AI processing queued for ticket %s.", ticket_id)

    return {
        "ticketId": ticket_id,
        "message": f"AI processing queued for ticket {ticket_id}.",
        "previousStatus": current_status,
    }


# ═════════════════════════════════════════════════════════════════
# POST /api/tickets/{ticket_id}/process-invoice — Trigger Stage C
# ═════════════════════════════════════════════════════════════════

@router.post("/{ticket_id}/process-invoice")
async def trigger_invoice_processing(ticket_id: str, background_tasks: BackgroundTasks):
    """
    Trigger Stage C (Invoice Processing) for a ticket.

    The ticket must be in 'ai_processed' status. This endpoint:
      1. Validates the ticket status.
      2. Queues the invoice processing as a background task.
      3. Returns immediately with a queued confirmation.

    The background task calls the Stage C Azure Function which runs
    the Foundry Agent V2 to validate the invoice, submit payment,
    and record results.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    current_status = doc.get("status", "")
    if current_status not in ("ai_processed", "invoice_processing", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Ticket is in status '{current_status}', must be 'ai_processed' to trigger invoice processing.",
        )

    # Queue the processing as a background task
    background_tasks.add_task(invoice_processing.trigger_invoice_processing, ticket_id)
    logger.info("Invoice processing queued for ticket %s.", ticket_id)

    return {
        "ticketId": ticket_id,
        "message": f"Invoice processing queued for ticket {ticket_id}.",
        "previousStatus": current_status,
    }


# ═══════════════════════════════════════════════════════════════════
# GET /api/tickets/{ticket_id}/invoice-processing — Stage C results
# ═══════════════════════════════════════════════════════════════════

@router.get("/{ticket_id}/invoice-processing")
async def get_invoice_processing_results(ticket_id: str):
    """
    Get invoice processing results for a ticket (Stage C: Tab 4).

    Returns the validation results, payment submission status,
    and any errors from the Invoice Processing Agent.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    return {
        "ticketId": ticket_id,
        "status": doc.get("status"),
        "invoiceProcessing": doc.get("invoiceProcessing"),
    }


# ═══════════════════════════════════════════════════════════════════
# POST /api/tickets/{ticket_id}/reprocess — Re-trigger processing
# ═══════════════════════════════════════════════════════════════════

@router.post("/{ticket_id}/reprocess")
async def reprocess_ticket(ticket_id: str, background_tasks: BackgroundTasks):
    """
    Manually re-trigger processing for a ticket.

    Resets the ticket status to 'ingested', downloads the PDF from
    Blob Storage, and re-triggers the Stage A extraction pipeline.
    """
    doc = storage.get_ticket(ticket_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")

    try:
        storage.update_ticket(ticket_id, {
            "status": TicketStatus.INGESTED.value,
            "extraction": {"status": "pending"},
            "aiProcessing": {"status": "pending"},
            "invoiceProcessing": {"status": "pending"},
        })
    except Exception as e:
        logger.error("Failed to reprocess ticket %s: %s", ticket_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to reprocess: {e}")

    # Re-trigger extraction if the ticket has an attachment in Blob Storage
    attachments = doc.get("attachments") or []
    if attachments:
        att = attachments[0]
        blob_name = f"{ticket_id}/{att.get('filename', '')}"
        try:
            pdf_bytes = blob_storage.download_blob(blob_name)
            background_tasks.add_task(
                extraction.process_extraction,
                ticket_id=ticket_id,
                pdf_bytes=pdf_bytes,
                blob_name=blob_name,
            )
            logger.info("Re-extraction queued for ticket %s.", ticket_id)
        except Exception as e:
            logger.warning(
                "Could not download blob for re-extraction of %s: %s", ticket_id, e,
            )

    return {"ticketId": ticket_id, "message": "Ticket queued for reprocessing."}


# ═══════════════════════════════════════════════════════════════════
# DELETE /api/tickets/{ticket_id} — Delete a ticket
# ═══════════════════════════════════════════════════════════════════

@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: str):
    """Delete a ticket by ID."""
    deleted = storage.delete_ticket(ticket_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    return {"ticketId": ticket_id, "message": "Ticket deleted."}
