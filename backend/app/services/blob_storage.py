"""
Azure Blob Storage service for PDF invoice file management.

Handles:
  • Uploading PDF files submitted via the ticket ingestion form.
  • Generating SAS URLs for Azure Content Understanding to access PDFs.
  • Retrieving file metadata.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Singleton Client
# ═══════════════════════════════════════════════════════════════════

_blob_service_client: Optional[BlobServiceClient] = None


def get_blob_service_client() -> BlobServiceClient:
    """Return the singleton BlobServiceClient.

    Supports two authentication modes:
      1. Connection string (blob_connection_string is set)
      2. Managed Identity (azure_storage_blob_endpoint + azure_client_id)
    """
    global _blob_service_client
    if _blob_service_client is None:
        settings = get_settings()
        if settings.blob_connection_string:
            _blob_service_client = BlobServiceClient.from_connection_string(
                settings.blob_connection_string,
            )
            logger.info("Blob Storage client created (connection string).")
        elif settings.azure_storage_blob_endpoint and settings.azure_client_id:
            from azure.identity import ManagedIdentityCredential
            credential = ManagedIdentityCredential(client_id=settings.azure_client_id)
            _blob_service_client = BlobServiceClient(
                account_url=settings.azure_storage_blob_endpoint,
                credential=credential,
            )
            logger.info("Blob Storage client created (Managed Identity).")
        elif settings.azure_storage_blob_endpoint:
            from azure.identity import DefaultAzureCredential
            _blob_service_client = BlobServiceClient(
                account_url=settings.azure_storage_blob_endpoint,
                credential=DefaultAzureCredential(),
            )
            logger.info("Blob Storage client created (DefaultAzureCredential).")
        else:
            raise RuntimeError("No Blob Storage credentials configured.")
    return _blob_service_client


def initialize_blob_storage() -> None:
    """Ensure the blob container exists. Called at app startup."""
    settings = get_settings()
    if not settings.blob_configured:
        logger.warning(
            "Blob Storage not configured — Blob Storage features disabled. "
            "PDFs will be stored locally as a fallback."
        )
        return

    client = get_blob_service_client()
    container_client = client.get_container_client(settings.blob_container_name)
    try:
        if not container_client.exists():
            container_client.create_container()
            logger.info("Created blob container '%s'.", settings.blob_container_name)
        else:
            logger.info("Blob container '%s' already exists.", settings.blob_container_name)
    except Exception as e:
        logger.warning("Could not verify blob container: %s (may need RBAC)", e)


def close_blob_storage() -> None:
    """Close the Blob Storage client."""
    global _blob_service_client
    if _blob_service_client:
        _blob_service_client.close()
        _blob_service_client = None
        logger.info("Blob Storage client closed.")


# ═══════════════════════════════════════════════════════════════════
# Upload / Download / SAS Operations
# ═══════════════════════════════════════════════════════════════════

def upload_pdf(
    ticket_id: str,
    filename: str,
    file_bytes: bytes,
) -> dict:
    """
    Upload a PDF file to Azure Blob Storage.

    Blob naming convention: {ticket_id}/{filename}
    This ensures each ticket's files are logically grouped.

    Args:
        ticket_id: The ticket ID (used as virtual directory prefix).
        filename: Original filename of the PDF.
        file_bytes: Raw bytes of the PDF file.

    Returns:
        dict with 'blob_url', 'blob_name', and 'size_bytes'.
    """
    settings = get_settings()

    # Fallback: if no Blob Storage configured, return a placeholder
    if not settings.blob_configured:
        logger.warning("Blob Storage not configured — returning local placeholder URL.")
        return {
            "blob_url": f"local://invoices/{ticket_id}/{filename}",
            "blob_name": f"{ticket_id}/{filename}",
            "size_bytes": len(file_bytes),
        }

    client = get_blob_service_client()
    container_client = client.get_container_client(settings.blob_container_name)

    blob_name = f"{ticket_id}/{filename}"
    blob_client = container_client.get_blob_client(blob_name)

    content_settings = ContentSettings(content_type="application/pdf")

    blob_client.upload_blob(
        data=file_bytes,
        overwrite=True,
        content_settings=content_settings,
    )

    blob_url = blob_client.url
    logger.info(
        "Uploaded PDF: %s (%d bytes) → %s",
        filename, len(file_bytes), blob_url,
    )

    return {
        "blob_url": blob_url,
        "blob_name": blob_name,
        "size_bytes": len(file_bytes),
    }


def generate_sas_url(blob_name: str, expiry_hours: int = 1) -> str:
    """
    Generate a SAS URL for a blob, allowing read-only access.

    Used to give Azure Content Understanding temporary access to the PDF.
    Supports two modes:
      1. Account key SAS (when blob_connection_string is set)
      2. User Delegation SAS (when using Managed Identity)

    Args:
        blob_name: Full blob name (e.g., "ZAVA-2026-00001/invoice.pdf").
        expiry_hours: How many hours the SAS token should be valid.

    Returns:
        Full URL with SAS token.
    """
    settings = get_settings()
    client = get_blob_service_client()
    container_client = client.get_container_client(settings.blob_container_name)
    blob_client = container_client.get_blob_client(blob_name)
    account_name = client.account_name

    expiry_time = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
    start_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    if settings.blob_connection_string:
        # Account key SAS (local dev)
        account_key = _extract_account_key(settings.blob_connection_string)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=settings.blob_container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
        )
        logger.info("Generated SAS URL (account key) for %s", blob_name)
    else:
        # User Delegation SAS (Managed Identity in production)
        user_delegation_key = client.get_user_delegation_key(
            key_start_time=start_time,
            key_expiry_time=expiry_time,
        )
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=settings.blob_container_name,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            start=start_time,
            expiry=expiry_time,
        )
        logger.info("Generated SAS URL (user delegation) for %s", blob_name)

    sas_url = f"{blob_client.url}?{sas_token}"
    return sas_url


def get_blob_metadata(blob_name: str) -> Optional[dict]:
    """Get metadata for a blob (size, content type, etc.)."""
    settings = get_settings()
    if not settings.blob_configured:
        return None

    client = get_blob_service_client()
    container_client = client.get_container_client(settings.blob_container_name)
    blob_client = container_client.get_blob_client(blob_name)

    try:
        props = blob_client.get_blob_properties()
        return {
            "size_bytes": props.size,
            "content_type": props.content_settings.content_type,
            "created_on": props.creation_time.isoformat() if props.creation_time else None,
            "last_modified": props.last_modified.isoformat() if props.last_modified else None,
        }
    except Exception as e:
        logger.error("Error getting blob metadata for %s: %s", blob_name, e)
        return None


def download_blob(blob_name: str) -> bytes:
    """
    Download a blob's content as bytes.

    Used by the reprocess endpoint to re-download the PDF from
    Blob Storage when re-triggering extraction.

    Raises:
        RuntimeError: If Blob Storage is not configured.
        Exception: If the download fails.
    """
    settings = get_settings()
    if not settings.blob_configured:
        raise RuntimeError("Blob Storage not configured — cannot download blob.")

    client = get_blob_service_client()
    container_client = client.get_container_client(settings.blob_container_name)
    blob_client = container_client.get_blob_client(blob_name)

    logger.info("Downloading blob: %s", blob_name)
    download_stream = blob_client.download_blob()
    data = download_stream.readall()
    logger.info("Downloaded %d bytes from %s", len(data), blob_name)
    return data


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _extract_account_key(connection_string: str) -> str:
    """Extract the AccountKey from a storage connection string."""
    for part in connection_string.split(";"):
        if part.strip().startswith("AccountKey="):
            return part.strip().split("=", 1)[1]
    raise ValueError("Could not extract AccountKey from connection string.")
