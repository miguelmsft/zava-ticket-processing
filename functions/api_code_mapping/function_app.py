"""
Code Mapping REST API — Azure Function

Provides HTTP endpoints for looking up standardized codes used by
Zava Processing Inc. This API is called by Foundry Agent V2 as an
OpenAPI tool via APIM AI Gateway.

Endpoints:
  GET /api/codes/{mapping_type}            — List all codes for a type
  GET /api/codes/{mapping_type}/{code}     — Look up a specific code
  GET /api/codes                           — List available mapping types

Mapping types: vendor_codes, product_codes, department_codes, action_codes

Reference data loaded from Cosmos DB (code-mappings container)
or falls back to embedded JSON if Cosmos is unavailable.
"""

import json
import logging
import os
from typing import Optional

import azure.functions as func
from azure.cosmos import CosmosClient, exceptions

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Cosmos DB connection
# ═══════════════════════════════════════════════════════════════════

COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_KEY = os.environ.get("COSMOS_KEY", "")
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "zava-ticket-processing")
COSMOS_USE_EMULATOR = os.environ.get("COSMOS_USE_EMULATOR", "false").lower() == "true"
CODE_MAPPINGS_CONTAINER = "code-mappings"

_cosmos_client: Optional[CosmosClient] = None
_database = None

# In-memory cache for code mappings (loaded once, refreshed on demand)
_code_mappings_cache: Optional[dict] = None


def _get_cosmos_client() -> CosmosClient:
    """Return singleton CosmosClient."""
    global _cosmos_client
    if _cosmos_client is None:
        kwargs = {}
        if COSMOS_USE_EMULATOR:
            kwargs["connection_verify"] = False
        _cosmos_client = CosmosClient(
            url=COSMOS_ENDPOINT,
            credential=COSMOS_KEY,
            **kwargs,
        )
    return _cosmos_client


def _get_code_mappings_container():
    """Return the code-mappings container proxy."""
    global _database
    if _database is None:
        _database = _get_cosmos_client().get_database_client(COSMOS_DATABASE)
    return _database.get_container_client(CODE_MAPPINGS_CONTAINER)


# ═══════════════════════════════════════════════════════════════════
# Fallback embedded data (for local dev without Cosmos)
# ═══════════════════════════════════════════════════════════════════

_FALLBACK_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "code_mappings.json",
)


def _load_fallback_data() -> dict:
    """Load code mappings from embedded JSON file."""
    try:
        with open(_FALLBACK_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Fallback code_mappings.json not found at %s", _FALLBACK_DATA_PATH)
        return {}


def _load_code_mappings() -> dict:
    """
    Load all code mappings — from Cosmos DB if available, else from fallback file.
    Results are cached in-memory for the function app lifetime.
    """
    global _code_mappings_cache
    if _code_mappings_cache is not None:
        return _code_mappings_cache

    # Try Cosmos DB first
    if COSMOS_ENDPOINT and COSMOS_KEY:
        try:
            container = _get_code_mappings_container()
            items = list(container.read_all_items())
            # Code mappings are stored as individual docs with mappingType field
            mappings = {}
            for item in items:
                mapping_type = item.get("mappingType", "")
                if mapping_type:
                    mappings[mapping_type] = {
                        "description": item.get("description", ""),
                        "mappings": item.get("mappings", {}),
                    }
            if mappings:
                _code_mappings_cache = mappings
                logger.info("Loaded %d mapping types from Cosmos DB", len(mappings))
                return mappings
        except Exception as e:
            logger.warning("Could not load from Cosmos DB, using fallback: %s", e)

    # Fallback to embedded JSON
    _code_mappings_cache = _load_fallback_data()
    logger.info("Loaded code mappings from fallback file (%d types)", len(_code_mappings_cache))
    return _code_mappings_cache


# ═══════════════════════════════════════════════════════════════════
# HTTP Route: List available mapping types
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="codes",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION,
)
def list_mapping_types(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/codes — List available mapping types with descriptions."""
    mappings = _load_code_mappings()
    result = {
        "mappingTypes": [
            {
                "type": mtype,
                "description": data.get("description", ""),
                "codeCount": len(data.get("mappings", {})),
            }
            for mtype, data in mappings.items()
        ]
    }
    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json",
        status_code=200,
    )


# ═══════════════════════════════════════════════════════════════════
# HTTP Route: List all codes for a mapping type
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="codes/{mapping_type}",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION,
)
def list_codes_by_type(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/codes/{mapping_type} — List all codes for the given mapping type."""
    mapping_type = req.route_params.get("mapping_type", "")
    mappings = _load_code_mappings()

    if mapping_type not in mappings:
        return func.HttpResponse(
            json.dumps({
                "error": f"Unknown mapping type: '{mapping_type}'",
                "available": list(mappings.keys()),
            }),
            mimetype="application/json",
            status_code=404,
        )

    type_data = mappings[mapping_type]
    return func.HttpResponse(
        json.dumps({
            "mappingType": mapping_type,
            "description": type_data.get("description", ""),
            "mappings": type_data.get("mappings", {}),
        }),
        mimetype="application/json",
        status_code=200,
    )


# ═══════════════════════════════════════════════════════════════════
# HTTP Route: Look up a specific code
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="codes/{mapping_type}/{code}",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION,
)
def lookup_code(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/codes/{mapping_type}/{code} — Look up a specific code.

    For vendor_codes: code is the vendor name (e.g., "ABC Industrial Supplies")
    For product_codes: code is the raw product code (e.g., "VLV-4200-IND")
    For department_codes: code is the category (e.g., "Valves & Flow Control")
    For action_codes: code is the condition key (e.g., "valid_invoice_all_checks_pass")
    """
    mapping_type = req.route_params.get("mapping_type", "")
    code = req.route_params.get("code", "")
    mappings = _load_code_mappings()

    if mapping_type not in mappings:
        return func.HttpResponse(
            json.dumps({
                "error": f"Unknown mapping type: '{mapping_type}'",
                "available": list(mappings.keys()),
            }),
            mimetype="application/json",
            status_code=404,
        )

    type_mappings = mappings[mapping_type].get("mappings", {})

    if code not in type_mappings:
        # Try case-insensitive match
        matched_key = None
        for key in type_mappings:
            if key.lower() == code.lower():
                matched_key = key
                break

        if matched_key is None:
            return func.HttpResponse(
                json.dumps({
                    "error": f"Code '{code}' not found in '{mapping_type}'",
                    "availableCodes": list(type_mappings.keys()),
                }),
                mimetype="application/json",
                status_code=404,
            )
        code = matched_key

    result = type_mappings[code]
    return func.HttpResponse(
        json.dumps({
            "mappingType": mapping_type,
            "inputCode": code,
            "result": result,
        }),
        mimetype="application/json",
        status_code=200,
    )


# ═══════════════════════════════════════════════════════════════════
# HTTP Route: Batch lookup — resolve multiple codes at once
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="codes/batch",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def batch_lookup(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/codes/batch — Resolve multiple codes in one request.

    Request body:
    {
        "lookups": [
            {"type": "vendor_codes", "code": "ABC Industrial Supplies"},
            {"type": "product_codes", "code": "VLV-4200-IND"},
            {"type": "department_codes", "code": "Valves & Flow Control"}
        ]
    }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            mimetype="application/json",
            status_code=400,
        )

    lookups = body.get("lookups", [])
    if not lookups:
        return func.HttpResponse(
            json.dumps({"error": "No lookups provided"}),
            mimetype="application/json",
            status_code=400,
        )

    mappings = _load_code_mappings()
    results = []

    for lookup in lookups:
        mtype = lookup.get("type", "")
        code = lookup.get("code", "")

        if mtype not in mappings:
            results.append({
                "type": mtype,
                "code": code,
                "found": False,
                "error": f"Unknown mapping type: '{mtype}'",
            })
            continue

        type_mappings = mappings[mtype].get("mappings", {})

        # Case-insensitive lookup
        matched_key = None
        for key in type_mappings:
            if key == code or key.lower() == code.lower():
                matched_key = key
                break

        if matched_key is None:
            results.append({
                "type": mtype,
                "code": code,
                "found": False,
            })
        else:
            results.append({
                "type": mtype,
                "code": matched_key,
                "found": True,
                "result": type_mappings[matched_key],
            })

    return func.HttpResponse(
        json.dumps({
            "lookupCount": len(lookups),
            "foundCount": sum(1 for r in results if r.get("found")),
            "results": results,
        }),
        mimetype="application/json",
        status_code=200,
    )
