"""
Seed Azure Cosmos DB with reference data for the Zava Processing demo.

This script:
  1. Creates the database and containers if they don't exist.
  2. Uploads code mappings into the `code-mappings` container.
  3. Optionally uploads sample tickets (without PDF blobs) into the `tickets` container.

Prerequisites:
    pip install azure-cosmos python-dotenv

Environment variables (or .env file):
    COSMOS_ENDPOINT   – e.g. https://<account>.documents.azure.com:443/
    COSMOS_KEY        – Primary key from Azure Portal
    COSMOS_DATABASE   – Database name (default: zava-ticket-processing)

Usage:
    python seed_cosmos.py                   # seed code-mappings only
    python seed_cosmos.py --with-tickets    # also seed sample tickets
    python seed_cosmos.py --emulator        # use local Cosmos DB emulator
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv

load_dotenv()

# ---------- paths ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_MAPPINGS_PATH = os.path.join(SCRIPT_DIR, "code_mappings.json")
SAMPLE_TICKETS_PATH = os.path.join(SCRIPT_DIR, "sample_tickets.json")

# ---------- emulator defaults ----------
EMULATOR_ENDPOINT = "https://localhost:8081"
EMULATOR_KEY = (
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
)

# ---------- database config ----------
DEFAULT_DATABASE = "zava-ticket-processing"
CONTAINERS = {
    "tickets": {
        "partition_key": "/ticketId",
        "unique_keys": None,
    },
    "code-mappings": {
        "partition_key": "/mappingType",
        "unique_keys": None,
    },
    "metrics": {
        "partition_key": "/metricType",
        "unique_keys": None,
    },
}


def get_cosmos_client(use_emulator: bool = False) -> CosmosClient:
    """Create and return a CosmosClient."""
    if use_emulator:
        print("🔗 Connecting to Cosmos DB Emulator...")
        return CosmosClient(
            EMULATOR_ENDPOINT,
            credential=EMULATOR_KEY,
            connection_verify=False,
        )

    endpoint = os.getenv("COSMOS_ENDPOINT")
    key = os.getenv("COSMOS_KEY")

    if not endpoint or not key:
        print("❌ Error: COSMOS_ENDPOINT and COSMOS_KEY environment variables are required.")
        print("   Set them in a .env file or export them in your shell.")
        print("   Or use --emulator flag for local development.")
        sys.exit(1)

    print(f"🔗 Connecting to Cosmos DB at {endpoint}...")
    return CosmosClient(endpoint, credential=key)


def ensure_database_and_containers(client: CosmosClient, db_name: str):
    """Create the database and containers if they do not exist."""
    print(f"\n📦 Ensuring database '{db_name}' exists...")
    database = client.create_database_if_not_exists(id=db_name)

    for container_name, config in CONTAINERS.items():
        print(f"   📁 Ensuring container '{container_name}' exists...")
        kwargs = {
            "id": container_name,
            "partition_key": PartitionKey(path=config["partition_key"]),
        }
        if config.get("unique_keys"):
            kwargs["unique_key_policy"] = {"uniqueKeys": config["unique_keys"]}

        database.create_container_if_not_exists(**kwargs)

    print("   ✅ All containers ready.\n")
    return database


def seed_code_mappings(database, code_mappings: dict):
    """Upload code mappings as individual documents to the code-mappings container."""
    container = database.get_container_client("code-mappings")
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for mapping_type, mapping_data in code_mappings.items():
        doc = {
            "id": f"mapping-{mapping_type}",
            "mappingType": mapping_type,
            "data": mapping_data,
            "createdAt": now,
            "updatedAt": now,
            "version": "1.0.0",
        }

        try:
            container.upsert_item(doc)
            count += 1
            item_count = len(mapping_data) if isinstance(mapping_data, (list, dict)) else 1
            print(f"   ✅ {mapping_type}: {item_count} entries")
        except exceptions.CosmosHttpResponseError as e:
            print(f"   ❌ {mapping_type}: {e.message}")

    print(f"\n   📊 Seeded {count} mapping documents.\n")


def seed_sample_tickets(database, tickets: list, storage_account_name: str = "zavastor"):
    """Upload sample ticket documents to the tickets container."""
    container = database.get_container_client("tickets")
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for ticket in tickets:
        # Build the Cosmos DB document matching architecture/ARCHITECTURE.md schema
        doc = {
            "id": ticket["ticketId"],
            "ticketId": ticket["ticketId"],
            "status": "ingested",
            "createdAt": now,
            "updatedAt": now,

            # Stage A – Extraction (populated by extraction pipeline)
            "raw": {
                "title": ticket["title"],
                "description": ticket["description"],
                "tags": ticket["tags"],
                "priority": ticket["priority"],
                "submitter": ticket["submitter"],
                "submitterName": ticket["submitterName"],
                "submitterDepartment": ticket["submitterDepartment"],
            },
            "attachments": [
                {
                    "filename": ticket["attachmentFilename"],
                    "blobUrl": f"https://{storage_account_name}.blob.core.windows.net/invoices/{ticket['attachmentFilename']}",
                    "contentType": "application/pdf",
                    "sizeBytes": 0,  # Will be updated when actual PDF is uploaded
                }
            ],
            "extraction": {
                "status": "pending",
                "completedAt": None,
                "invoiceData": None,
                "confidence": None,
            },

            # Stage B – AI Processing (populated by information-processing agent)
            "aiProcessing": {
                "status": "pending",
                "completedAt": None,
                "standardizedCodes": None,
                "summary": None,
                "nextAction": None,
            },

            # Stage C – Invoice Processing (populated by invoice-processing agent)
            "invoiceProcessing": {
                "status": "pending",
                "completedAt": None,
                "validationResults": None,
                "paymentStatus": None,
                "paymentReference": None,
            },

            # Metadata for demo
            "_demo": {
                "scenario": ticket["scenario"],
                "scenarioDescription": ticket["scenarioDescription"],
                "expectedOutcome": ticket["expectedOutcome"],
            },
        }

        try:
            container.upsert_item(doc)
            count += 1
            print(f"   ✅ {ticket['ticketId']}: {ticket['title'][:55]}...")
        except exceptions.CosmosHttpResponseError as e:
            print(f"   ❌ {ticket['ticketId']}: {e.message}")

    print(f"\n   📊 Seeded {count} ticket documents.\n")


def main():
    parser = argparse.ArgumentParser(description="Seed Cosmos DB for Zava Processing demo")
    parser.add_argument(
        "--with-tickets",
        action="store_true",
        help="Also seed sample ticket documents",
    )
    parser.add_argument(
        "--emulator",
        action="store_true",
        help="Use the local Cosmos DB Emulator",
    )
    parser.add_argument(
        "--database",
        default=os.getenv("COSMOS_DATABASE", DEFAULT_DATABASE),
        help=f"Database name (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--storage-account",
        default=os.getenv("STORAGE_ACCOUNT_NAME", "zavastor"),
        help="Storage account name for blob URLs (default: zavastor or STORAGE_ACCOUNT_NAME env var)",
    )
    args = parser.parse_args()

    # Load data
    print("📂 Loading data files...")
    with open(CODE_MAPPINGS_PATH, "r", encoding="utf-8") as f:
        code_mappings = json.load(f)
    print(f"   Code mappings: {len(code_mappings)} categories")

    if args.with_tickets:
        with open(SAMPLE_TICKETS_PATH, "r", encoding="utf-8") as f:
            sample_tickets = json.load(f)
        print(f"   Sample tickets: {len(sample_tickets)} tickets")

    # Connect
    client = get_cosmos_client(use_emulator=args.emulator)

    # Setup
    database = ensure_database_and_containers(client, args.database)

    # Seed
    print("🌱 Seeding code mappings...")
    seed_code_mappings(database, code_mappings)

    if args.with_tickets:
        print("🌱 Seeding sample tickets...")
        seed_sample_tickets(database, sample_tickets, storage_account_name=args.storage_account)

    print("🎉 Seeding complete!")


if __name__ == "__main__":
    main()
