"""
postdeploy.py — Post-deployment setup for Zava Ticket Processing
=================================================================
This script runs automatically after `azd deploy` (via azure.yaml hooks).

It performs:
  1. Seeds Cosmos DB with code_mappings reference data
  2. Seeds Cosmos DB with initial metrics structure
  3. Validates all deployed service endpoints (health checks)
  4. Prints a summary of the deployment

Usage:
  python scripts/postdeploy.py          # Reads config from azd env
  python scripts/postdeploy.py --dry-run  # Print what would be done
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Fix encoding for Windows PowerShell 5 (cp1252 can't handle Unicode emojis)
# ---------------------------------------------------------------------------
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Configuration — read from azd environment variables
# ---------------------------------------------------------------------------

def get_azd_env(key: str, default: str = "") -> str:
    """Get a value from azd env or OS environment."""
    # First check OS env (set by azd during hooks)
    value = os.environ.get(key, "")
    if value:
        return value
    # Fallback: try azd env get-value
    try:
        result = subprocess.run(
            ["azd", "env", "get-value", key],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return default


# ---------------------------------------------------------------------------
# Code Mappings — reference data for AI Agent standardization
# ---------------------------------------------------------------------------

CODE_MAPPINGS = [
    {
        "id": "vendor-codes",
        "mappingType": "vendor",
        "description": "Vendor identification codes",
        "mappings": {
            "ZAVA-VND-001": {"name": "Acme Corp", "category": "Manufacturing", "region": "NA"},
            "ZAVA-VND-002": {"name": "GlobalTech Solutions", "category": "Technology", "region": "EU"},
            "ZAVA-VND-003": {"name": "Pacific Logistics", "category": "Shipping", "region": "APAC"},
            "ZAVA-VND-004": {"name": "Nordic Materials AS", "category": "Raw Materials", "region": "EU"},
            "ZAVA-VND-005": {"name": "Southern Cross Minerals", "category": "Mining", "region": "APAC"},
            "ZAVA-VND-006": {"name": "Midwest Fabrication Inc", "category": "Manufacturing", "region": "NA"},
            "ZAVA-VND-007": {"name": "Rhine Chemical GmbH", "category": "Chemicals", "region": "EU"},
            "ZAVA-VND-008": {"name": "Sakura Electronics", "category": "Electronics", "region": "APAC"},
        },
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "product-codes",
        "mappingType": "product",
        "description": "Product category classification codes",
        "mappings": {
            "PRD-EL-100": {"name": "Electronic Components", "unit": "pcs", "hsCode": "8542.31"},
            "PRD-CH-200": {"name": "Industrial Chemicals", "unit": "kg", "hsCode": "2903.11"},
            "PRD-MT-300": {"name": "Metal Alloys", "unit": "ton", "hsCode": "7202.11"},
            "PRD-PL-400": {"name": "Polymer Resins", "unit": "kg", "hsCode": "3901.10"},
            "PRD-TX-500": {"name": "Technical Textiles", "unit": "sqm", "hsCode": "5903.10"},
            "PRD-MC-600": {"name": "Machined Parts", "unit": "pcs", "hsCode": "8466.93"},
        },
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "department-codes",
        "mappingType": "department",
        "description": "Internal department routing codes",
        "mappings": {
            "DEPT-FIN": {"name": "Finance & Accounting", "approvalLimit": 50000},
            "DEPT-PROC": {"name": "Procurement", "approvalLimit": 100000},
            "DEPT-QA": {"name": "Quality Assurance", "approvalLimit": 25000},
            "DEPT-LOG": {"name": "Logistics & Shipping", "approvalLimit": 75000},
            "DEPT-LEG": {"name": "Legal & Compliance", "approvalLimit": 200000},
            "DEPT-ENG": {"name": "Engineering", "approvalLimit": 150000},
        },
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "action-codes",
        "mappingType": "action",
        "description": "Next action classification codes",
        "mappings": {
            "ACT-INV-PROC": {"name": "Process Invoice", "sla_hours": 24, "priority": "high"},
            "ACT-INV-REV": {"name": "Review Invoice", "sla_hours": 48, "priority": "medium"},
            "ACT-INV-ESC": {"name": "Escalate Invoice", "sla_hours": 4, "priority": "critical"},
            "ACT-INV-HOLD": {"name": "Hold for Approval", "sla_hours": 72, "priority": "low"},
            "ACT-DOC-REQ": {"name": "Request Documentation", "sla_hours": 48, "priority": "medium"},
            "ACT-VND-CONTACT": {"name": "Contact Vendor", "sla_hours": 24, "priority": "medium"},
            "ACT-CLOSE": {"name": "Close Ticket", "sla_hours": 8, "priority": "low"},
        },
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "currency-codes",
        "mappingType": "currency",
        "description": "Supported currency codes and exchange reference rates",
        "mappings": {
            "USD": {"name": "US Dollar", "symbol": "$", "refRate": 1.0},
            "EUR": {"name": "Euro", "symbol": "€", "refRate": 0.92},
            "GBP": {"name": "British Pound", "symbol": "£", "refRate": 0.79},
            "JPY": {"name": "Japanese Yen", "symbol": "¥", "refRate": 149.50},
            "AUD": {"name": "Australian Dollar", "symbol": "A$", "refRate": 1.53},
            "SEK": {"name": "Swedish Krona", "symbol": "kr", "refRate": 10.85},
            "NOK": {"name": "Norwegian Krone", "symbol": "kr", "refRate": 10.72},
        },
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
]

# ---------------------------------------------------------------------------
# Initial Metrics structure
# ---------------------------------------------------------------------------

INITIAL_METRICS = [
    {
        "id": "daily-summary",
        "metricType": "daily",
        "description": "Daily ticket processing metrics",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ticketsIngested": 0,
        "ticketsExtracted": 0,
        "ticketsProcessedAI": 0,
        "invoicesProcessed": 0,
        "invoicesApproved": 0,
        "invoicesRejected": 0,
        "avgProcessingTimeSec": 0.0,
        "errorCount": 0,
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "system-health",
        "metricType": "health",
        "description": "System health check results",
        "services": {},
        "lastChecked": datetime.now(timezone.utc).isoformat(),
    },
]


# ---------------------------------------------------------------------------
# Seed Cosmos DB
# ---------------------------------------------------------------------------

async def seed_cosmos_db(endpoint: str, database_name: str, dry_run: bool = False):
    """Seed Cosmos DB with code mappings and initial metrics."""
    print("\n── Seeding Cosmos DB ─────────────────────────────────────────")

    if dry_run:
        print(f"  [DRY RUN] Would seed {len(CODE_MAPPINGS)} code mappings to {endpoint}")
        print(f"  [DRY RUN] Would seed {len(INITIAL_METRICS)} metrics to {endpoint}")
        return True

    try:
        from azure.cosmos.aio import CosmosClient
        from azure.identity.aio import DefaultAzureCredential
    except ImportError:
        print("  ⚠ azure-cosmos or azure-identity not installed. Skipping Cosmos seed.")
        print("  Run: pip install azure-cosmos azure-identity")
        return False

    try:
        credential = DefaultAzureCredential()
        client = CosmosClient(endpoint, credential=credential)
        database = client.get_database_client(database_name)

        # Seed code-mappings container
        container = database.get_container_client("code-mappings")
        print(f"  Seeding code-mappings container ({len(CODE_MAPPINGS)} documents)...")
        for mapping in CODE_MAPPINGS:
            try:
                await container.upsert_item(mapping)
                print(f"    ✓ {mapping['id']} ({mapping['mappingType']})")
            except Exception as e:
                print(f"    ✗ {mapping['id']}: {e}")

        # Seed metrics container
        metrics_container = database.get_container_client("metrics")
        print(f"  Seeding metrics container ({len(INITIAL_METRICS)} documents)...")
        for metric in INITIAL_METRICS:
            try:
                await metrics_container.upsert_item(metric)
                print(f"    ✓ {metric['id']} ({metric['metricType']})")
            except Exception as e:
                print(f"    ✗ {metric['id']}: {e}")

        await credential.close()
        await client.close()
        print("  ✓ Cosmos DB seeded successfully")
        return True

    except Exception as e:
        print(f"  ✗ Failed to seed Cosmos DB: {e}")
        return False


# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------

async def check_endpoint(name: str, url: str, path: str = "/health") -> dict:
    """Check if a service endpoint is responding."""
    import aiohttp

    full_url = f"{url.rstrip('/')}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                status = resp.status
                healthy = 200 <= status < 400
                return {
                    "name": name,
                    "url": full_url,
                    "status": status,
                    "healthy": healthy,
                }
    except Exception as e:
        return {
            "name": name,
            "url": full_url,
            "status": 0,
            "healthy": False,
            "error": str(e),
        }


async def run_health_checks(endpoints: dict, dry_run: bool = False) -> list:
    """Run health checks against all deployed endpoints."""
    print("\n── Health Checks ─────────────────────────────────────────────")

    if dry_run:
        for name, url in endpoints.items():
            print(f"  [DRY RUN] Would check: {name} → {url}")
        return []

    try:
        import aiohttp  # noqa: F401
    except ImportError:
        print("  ⚠ aiohttp not installed. Skipping health checks.")
        print("  Run: pip install aiohttp")
        return []

    # Define check paths per service type
    check_paths = {
        "backend": "/health",
        "frontend": "/",
        "mcp-cosmos": "/runtime/webhooks/mcp",
        "api-code-mapping": "/api/health",
        "api-payment": "/api/health",
        "stage-b": "/api/health",
        "stage-c": "/api/health",
    }

    tasks = []
    for name, url in endpoints.items():
        if url and url != "N/A":
            path = check_paths.get(name, "/health")
            tasks.append(check_endpoint(name, url, path))

    if not tasks:
        print("  No endpoints to check.")
        return []

    results = await asyncio.gather(*tasks)

    for result in results:
        icon = "✓" if result["healthy"] else "✗"
        status = result.get("status", 0)
        error = result.get("error", "")
        extra = f" ({error})" if error else ""
        print(f"  {icon} {result['name']:20s} → HTTP {status}{extra}")

    healthy_count = sum(1 for r in results if r["healthy"])
    total = len(results)
    print(f"\n  {healthy_count}/{total} services healthy")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 65)
    print("  Zava Processing — Post-deployment Setup")
    print("=" * 65)

    if dry_run:
        print("  [DRY RUN MODE — no changes will be made]")

    # Read configuration from azd env
    cosmos_endpoint = get_azd_env("AZURE_COSMOS_ENDPOINT")
    cosmos_database = get_azd_env("AZURE_COSMOS_DATABASE_NAME", "zava-ticket-processing")
    backend_url = get_azd_env("SERVICE_BACKEND_URI")
    frontend_url = get_azd_env("SERVICE_FRONTEND_URI")
    mcp_cosmos_url = get_azd_env("SERVICE_MCP_COSMOS_URI")
    code_mapping_url = get_azd_env("SERVICE_API_CODE_MAPPING_URI")
    payment_url = get_azd_env("SERVICE_API_PAYMENT_URI")
    stage_b_url = get_azd_env("SERVICE_STAGE_B_URI")
    stage_c_url = get_azd_env("SERVICE_STAGE_C_URI")

    print(f"\n  Cosmos Endpoint:  {cosmos_endpoint or '(not set)'}")
    print(f"  Cosmos Database:  {cosmos_database}")
    print(f"  Backend URL:      {backend_url or '(not set)'}")
    print(f"  Frontend URL:     {frontend_url or '(not set)'}")

    # ── Step 1: Seed Cosmos DB ──────────────────────────────────────────
    if cosmos_endpoint:
        await seed_cosmos_db(cosmos_endpoint, cosmos_database, dry_run)
    else:
        print("\n  ⚠ AZURE_COSMOS_ENDPOINT not set. Skipping Cosmos DB seeding.")
        print("  Set it with: azd env set AZURE_COSMOS_ENDPOINT <endpoint>")

    # ── Step 2: Health Checks ───────────────────────────────────────────
    endpoints = {
        "backend": backend_url,
        "frontend": frontend_url,
        "mcp-cosmos": mcp_cosmos_url,
        "api-code-mapping": code_mapping_url,
        "api-payment": payment_url,
        "stage-b": stage_b_url,
        "stage-c": stage_c_url,
    }

    # Filter out empty endpoints
    active_endpoints = {k: v for k, v in endpoints.items() if v}
    if active_endpoints:
        await run_health_checks(active_endpoints, dry_run)
    else:
        print("\n  ⚠ No service URLs found. Skipping health checks.")

    # ── Summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  Post-deployment setup complete!")
    print("=" * 65)

    if frontend_url:
        print(f"\n  🌐 Open your app: {frontend_url}")
    if backend_url:
        print(f"  📡 API docs:      {backend_url}/docs")
    print("")


if __name__ == "__main__":
    asyncio.run(main())
