"""
Application configuration loaded from environment variables.

Uses pydantic-settings for typed, validated configuration with .env file support.
Supports both local dev env var names (COSMOS_ENDPOINT) and Azure Bicep
env var names (AZURE_COSMOS_ENDPOINT) via AliasChoices.
"""

from functools import lru_cache
from pydantic import AliasChoices
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings — loaded from environment variables or .env file."""

    # ── App ──────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Azure Cosmos DB ──────────────────────────────
    # Accepts COSMOS_ENDPOINT or AZURE_COSMOS_ENDPOINT
    cosmos_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("cosmos_endpoint", "azure_cosmos_endpoint"),
    )
    cosmos_key: str = Field(
        default="",
        validation_alias=AliasChoices("cosmos_key", "cosmos_db_key"),
    )
    # Accepts COSMOS_DATABASE or COSMOS_DATABASE_NAME
    cosmos_database: str = Field(
        default="zava-ticket-processing",
        validation_alias=AliasChoices("cosmos_database", "cosmos_database_name"),
    )
    cosmos_use_emulator: bool = False

    # ── Azure Managed Identity ───────────────────────
    azure_client_id: str = ""

    # ── Azure Blob Storage ───────────────────────────
    blob_connection_string: str = ""
    blob_container_name: str = "invoices"
    # Managed Identity blob access
    azure_storage_blob_endpoint: str = ""
    azure_storage_account_name: str = ""

    # ── Azure Content Understanding (Phase 4) ────────
    content_understanding_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("content_understanding_endpoint", "azure_ai_endpoint"),
    )
    content_understanding_key: str = ""

    # ── Azure AI Foundry (Phases 6-7) ────────────────
    ai_project_endpoint: str = ""
    model_deployment_name: str = "gpt-4o"

    # ── Stage B/C Azure Function endpoints ────────────
    stage_b_function_url: str = "http://localhost:7074/api/process-ticket"
    stage_b_function_key: str = ""
    stage_c_function_url: str = "http://localhost:7075/api/process-invoice"
    stage_c_function_key: str = ""

    # ── Reliability settings ─────────────────────────
    # When True, the backend will NOT fall back to local simulation
    # when Azure Functions return non-200 responses. Instead it will
    # retry once (on 503) and then return an error.
    disable_simulation_fallback: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def use_managed_identity(self) -> bool:
        """True when Managed Identity is configured (AZURE_CLIENT_ID set)."""
        return bool(self.azure_client_id)

    @property
    def cosmos_configured(self) -> bool:
        """True when Cosmos DB can be used (endpoint + key or Managed Identity)."""
        return bool(self.cosmos_endpoint) and (bool(self.cosmos_key) or self.use_managed_identity)

    @property
    def blob_configured(self) -> bool:
        """True when Blob Storage can be used (connection string or Managed Identity)."""
        return bool(self.blob_connection_string) or (
            bool(self.azure_storage_blob_endpoint) and self.use_managed_identity
        )

    @property
    def content_understanding_configured(self) -> bool:
        """True when Content Understanding can be used (endpoint + key OR endpoint + Managed Identity)."""
        if not self.content_understanding_endpoint:
            return False
        # API key auth
        if self.content_understanding_key:
            return True
        # Managed Identity auth (no key needed)
        return self.use_managed_identity

    @property
    def stage_b_url(self) -> str:
        """Stage B function URL with /api/process-ticket path ensured."""
        url = self.stage_b_function_url
        if url and not url.rstrip("/").endswith("/api/process-ticket"):
            return url.rstrip("/") + "/api/process-ticket"
        return url

    @property
    def stage_c_url(self) -> str:
        """Stage C function URL with /api/process-invoice path ensured."""
        url = self.stage_c_function_url
        if url and not url.rstrip("/").endswith("/api/process-invoice"):
            return url.rstrip("/") + "/api/process-invoice"
        return url


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
