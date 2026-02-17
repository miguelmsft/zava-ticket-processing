"""
Phase 5 — Unit tests for all three Azure Functions.

Tests the core business logic of each function WITHOUT the Azure Functions
runtime. We import from the extracted logic modules that have zero
dependency on azure.functions / azure.cosmos.

Run: python -m pytest functions/tests/test_functions.py -v
  or: python functions/tests/test_functions.py
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

# ═══════════════════════════════════════════════════════════════════
# Path setup for local imports
# ═══════════════════════════════════════════════════════════════════

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_FUNCTIONS_DIR = os.path.normpath(os.path.join(_TESTS_DIR, ".."))

# Add logic module directories to path
_payment_dir = os.path.join(_FUNCTIONS_DIR, "api_payment")
_mcp_dir = os.path.join(_FUNCTIONS_DIR, "mcp_cosmos")

for d in (_payment_dir, _mcp_dir):
    if d not in sys.path:
        sys.path.insert(0, d)


# ═══════════════════════════════════════════════════════════════════
# Test 1: Code Mapping API — Logic Tests
# ═══════════════════════════════════════════════════════════════════


class TestCodeMappingLogic(unittest.TestCase):
    """Tests for code mapping lookup logic."""

    @classmethod
    def setUpClass(cls):
        """Load the code mappings JSON once for all tests."""
        mappings_path = os.path.join(_FUNCTIONS_DIR, "..", "data", "code_mappings.json")
        with open(os.path.normpath(mappings_path), "r", encoding="utf-8") as f:
            cls.mappings = json.load(f)

    def test_vendor_codes_count(self):
        """Should have 6 vendor codes."""
        self.assertEqual(len(self.mappings["vendor_codes"]["mappings"]), 6)

    def test_product_codes_count(self):
        """Should have 20 product codes."""
        self.assertEqual(len(self.mappings["product_codes"]["mappings"]), 20)

    def test_department_codes_count(self):
        """Should have 11 department codes."""
        self.assertEqual(len(self.mappings["department_codes"]["mappings"]), 11)

    def test_action_codes_count(self):
        """Should have 7 action codes."""
        self.assertEqual(len(self.mappings["action_codes"]["mappings"]), 7)

    def test_vendor_lookup_abc(self):
        """ABC Industrial Supplies should map to ABCIND-001."""
        vendor = self.mappings["vendor_codes"]["mappings"]["ABC Industrial Supplies"]
        self.assertEqual(vendor["vendorCode"], "ABCIND-001")
        self.assertTrue(vendor["approved"])

    def test_vendor_lookup_greenfield_unapproved(self):
        """Greenfield Environmental Services should be NOT approved."""
        vendor = self.mappings["vendor_codes"]["mappings"]["Greenfield Environmental Services"]
        self.assertEqual(vendor["vendorCode"], "GRNENV-006")
        self.assertFalse(vendor["approved"])

    def test_product_code_standardization(self):
        """VLV-4200-IND should standardize to ZAVA-VLV-4200-IND-STD."""
        product = self.mappings["product_codes"]["mappings"]["VLV-4200-IND"]
        self.assertEqual(product["standardCode"], "ZAVA-VLV-4200-IND-STD")

    def test_product_code_hazardous_flag(self):
        """CHEM-HCL-500 should be flagged as hazardous."""
        product = self.mappings["product_codes"]["mappings"]["CHEM-HCL-500"]
        self.assertTrue(product.get("hazardous", False))

    def test_department_mapping(self):
        """Valves & Flow Control should map to PROC-MFG-001."""
        dept = self.mappings["department_codes"]["mappings"]["Valves & Flow Control"]
        self.assertEqual(dept["departmentCode"], "PROC-MFG-001")
        self.assertEqual(dept["costCenter"], "CC-4500")

    def test_action_code_invoice_processing(self):
        """valid_invoice_all_checks_pass should lead to invoice_processing."""
        action = self.mappings["action_codes"]["mappings"]["valid_invoice_all_checks_pass"]
        self.assertEqual(action["nextAction"], "invoice_processing")

    def test_action_code_vendor_not_approved(self):
        """vendor_not_approved should lead to vendor_approval."""
        action = self.mappings["action_codes"]["mappings"]["vendor_not_approved"]
        self.assertEqual(action["nextAction"], "vendor_approval")

    def test_action_code_amount_discrepancy(self):
        """amount_discrepancy_detected should lead to manual_review."""
        action = self.mappings["action_codes"]["mappings"]["amount_discrepancy_detected"]
        self.assertEqual(action["nextAction"], "manual_review")


# ═══════════════════════════════════════════════════════════════════
# Test 2: Payment Processing API — Validation Logic
# ═══════════════════════════════════════════════════════════════════


from payment_logic import (
    validate_invoice_number,
    validate_amount,
    validate_due_date,
    validate_vendor,
    APPROVED_VENDORS,
)


class TestPaymentValidation(unittest.TestCase):
    """Tests for payment validation logic (imported from payment_logic)."""

    def test_valid_invoice_number(self):
        """INV-2026-78432 should be valid."""
        result = validate_invoice_number("INV-2026-78432")
        self.assertTrue(result["valid"])

    def test_invalid_invoice_number_format(self):
        """ABC-123 should be invalid."""
        result = validate_invoice_number("ABC-123")
        self.assertFalse(result["valid"])

    def test_empty_invoice_number(self):
        """Empty invoice number should be invalid."""
        result = validate_invoice_number("")
        self.assertFalse(result["valid"])

    def test_valid_amount(self):
        """$13,531.25 should be valid."""
        result = validate_amount(13531.25)
        self.assertTrue(result["valid"])

    def test_zero_amount(self):
        """$0 should be invalid."""
        result = validate_amount(0)
        self.assertFalse(result["valid"])

    def test_negative_amount(self):
        """Negative amount should be invalid."""
        result = validate_amount(-500)
        self.assertFalse(result["valid"])

    def test_amount_over_limit(self):
        """Amount over $100,000 should be invalid."""
        result = validate_amount(150000)
        self.assertFalse(result["valid"])

    def test_valid_future_due_date(self):
        """A future date should be valid and not past due."""
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        result = validate_due_date(future_date)
        self.assertTrue(result["valid"])
        self.assertFalse(result["pastDue"])

    def test_recently_past_due_date(self):
        """A date 15 days ago should be valid but flagged as past due."""
        past_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
        result = validate_due_date(past_date)
        self.assertTrue(result["valid"])
        self.assertTrue(result["pastDue"])

    def test_very_past_due_date(self):
        """A date 120 days ago should be invalid (exceeds 90-day window)."""
        old_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        result = validate_due_date(old_date)
        self.assertFalse(result["valid"])

    def test_approved_vendor(self):
        """ABCIND-001 should be an approved vendor."""
        result = validate_vendor("ABCIND-001")
        self.assertTrue(result["valid"])
        self.assertIn("ABC Industrial Supplies", result["vendorName"])

    def test_unapproved_vendor(self):
        """GRNENV-006 should not be in the approved list."""
        result = validate_vendor("GRNENV-006")
        self.assertFalse(result["valid"])

    def test_unknown_vendor(self):
        """Unknown vendor code should not be approved."""
        result = validate_vendor("UNKNOWN-999")
        self.assertFalse(result["valid"])


# ═══════════════════════════════════════════════════════════════════
# Test 3: MCP Cosmos Server — Tool JSON Protocol
# ═══════════════════════════════════════════════════════════════════


from cosmos_helpers import (
    clean_doc,
    deep_merge,
    ToolProperty,
    parse_mcp_context,
    READ_TICKET_PROPS,
    UPDATE_TICKET_PROPS,
    QUERY_STATUS_PROPS,
)


class TestMCPToolProtocol(unittest.TestCase):
    """Tests for MCP tool argument parsing and response format."""

    def test_read_ticket_args_parsing(self):
        """The MCP context should contain arguments.ticket_id."""
        context_json = json.dumps({
            "arguments": {"ticket_id": "ZAVA-2026-00001"}
        })
        args = parse_mcp_context(context_json)
        self.assertEqual(args["ticket_id"], "ZAVA-2026-00001")

    def test_update_ticket_args_parsing(self):
        """update_ticket should parse ticket_id and updates_json."""
        updates = {"status": "ai_processed", "aiProcessing": {"summary": "Test"}}
        context_json = json.dumps({
            "arguments": {
                "ticket_id": "ZAVA-2026-00001",
                "updates_json": json.dumps(updates),
            }
        })
        args = parse_mcp_context(context_json)
        self.assertEqual(args["ticket_id"], "ZAVA-2026-00001")
        parsed_updates = json.loads(args["updates_json"])
        self.assertEqual(parsed_updates["status"], "ai_processed")
        self.assertEqual(parsed_updates["aiProcessing"]["summary"], "Test")

    def test_query_status_args_parsing(self):
        """query_tickets_by_status should parse status and max_results."""
        context_json = json.dumps({
            "arguments": {"status": "extracted", "max_results": "5"}
        })
        args = parse_mcp_context(context_json)
        self.assertEqual(args["status"], "extracted")
        self.assertEqual(int(args["max_results"]), 5)

    def test_tool_properties_format(self):
        """Tool properties JSON should match Azure Functions MCP extension schema."""
        parsed = json.loads(READ_TICKET_PROPS)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["propertyName"], "ticket_id")
        self.assertEqual(parsed[0]["propertyType"], "string")

        update_parsed = json.loads(UPDATE_TICKET_PROPS)
        self.assertEqual(len(update_parsed), 2)
        prop_names = {p["propertyName"] for p in update_parsed}
        self.assertEqual(prop_names, {"ticket_id", "updates_json"})

        query_parsed = json.loads(QUERY_STATUS_PROPS)
        self.assertEqual(len(query_parsed), 2)
        prop_names = {p["propertyName"] for p in query_parsed}
        self.assertEqual(prop_names, {"status", "max_results"})

    def test_empty_ticket_id_returns_error(self):
        """An empty ticket_id should result in an error response."""
        context_json = json.dumps({"arguments": {"ticket_id": ""}})
        args = parse_mcp_context(context_json)
        self.assertEqual(args["ticket_id"], "")

    def test_clean_doc_removes_cosmos_metadata(self):
        """clean_doc should remove fields starting with underscore."""
        doc = {
            "id": "ZAVA-2026-00001",
            "ticketId": "ZAVA-2026-00001",
            "status": "extracted",
            "_rid": "some-rid",
            "_self": "some-self",
            "_etag": "some-etag",
            "_attachments": "attachments/",
            "_ts": 1234567890,
        }
        cleaned = clean_doc(doc)
        self.assertIn("id", cleaned)
        self.assertIn("ticketId", cleaned)
        self.assertIn("status", cleaned)
        self.assertNotIn("_rid", cleaned)
        self.assertNotIn("_self", cleaned)
        self.assertNotIn("_etag", cleaned)
        self.assertNotIn("_ts", cleaned)

    def test_clean_doc_handles_none(self):
        """clean_doc should return empty dict for None input."""
        self.assertEqual(clean_doc(None), {})

    def test_clean_doc_preserves_all_non_underscore(self):
        """clean_doc should keep all user fields including 'id'."""
        doc = {"id": "test", "name": "test", "nested": {"a": 1}, "_rid": "x"}
        cleaned = clean_doc(doc)
        self.assertEqual(len(cleaned), 3)
        self.assertIn("nested", cleaned)

    # ── deep_merge tests ──────────────────────────────────────────

    def test_deep_merge_top_level(self):
        """deep_merge should overwrite top-level scalar values."""
        base = {"status": "extracted", "title": "Old Title"}
        updates = {"status": "ai_processed"}
        deep_merge(base, updates)
        self.assertEqual(base["status"], "ai_processed")
        self.assertEqual(base["title"], "Old Title")  # untouched

    def test_deep_merge_nested_preserves_siblings(self):
        """deep_merge should NOT overwrite sibling keys in nested dicts."""
        base = {
            "aiProcessing": {
                "summary": "Old summary",
                "standardizedCodes": {"vendor": "V1"},
                "validations": {"dateCheck": "passed", "vendorCheck": "passed"},
            }
        }
        updates = {
            "aiProcessing": {
                "validations": {"amountCheck": "passed"},
            }
        }
        deep_merge(base, updates)
        # amountCheck should be added
        self.assertEqual(base["aiProcessing"]["validations"]["amountCheck"], "passed")
        # existing siblings should be preserved
        self.assertEqual(base["aiProcessing"]["validations"]["dateCheck"], "passed")
        self.assertEqual(base["aiProcessing"]["validations"]["vendorCheck"], "passed")
        # other aiProcessing keys untouched
        self.assertEqual(base["aiProcessing"]["summary"], "Old summary")
        self.assertEqual(base["aiProcessing"]["standardizedCodes"]["vendor"], "V1")

    def test_deep_merge_new_key(self):
        """deep_merge should add entirely new keys."""
        base = {"id": "ZAVA-001"}
        updates = {"invoiceProcessing": {"paymentId": "PAY-123"}}
        deep_merge(base, updates)
        self.assertEqual(base["invoiceProcessing"]["paymentId"], "PAY-123")
        self.assertEqual(base["id"], "ZAVA-001")

    def test_deep_merge_overwrite_non_dict_with_dict(self):
        """If base has a scalar and updates has a dict, updates wins."""
        base = {"field": "scalar_value"}
        updates = {"field": {"nested": True}}
        deep_merge(base, updates)
        self.assertEqual(base["field"], {"nested": True})

    def test_deep_merge_overwrite_dict_with_scalar(self):
        """If base has a dict and updates has a scalar, updates wins."""
        base = {"field": {"nested": True}}
        updates = {"field": "scalar_value"}
        deep_merge(base, updates)
        self.assertEqual(base["field"], "scalar_value")


# ═══════════════════════════════════════════════════════════════════
# Test 4: OpenAPI Spec Validation
# ═══════════════════════════════════════════════════════════════════


class TestOpenAPISpecs(unittest.TestCase):
    """Validate OpenAPI specs can be loaded and have expected structure."""

    @classmethod
    def setUpClass(cls):
        """Load both OpenAPI spec files."""
        import yaml

        specs_dir = os.path.join(_FUNCTIONS_DIR, "openapi")

        with open(os.path.join(specs_dir, "code_mapping_api.yaml"), "r") as f:
            cls.code_mapping_spec = yaml.safe_load(f)

        with open(os.path.join(specs_dir, "payment_api.yaml"), "r") as f:
            cls.payment_spec = yaml.safe_load(f)

    def test_code_mapping_spec_version(self):
        """Code mapping spec should be OpenAPI 3.0.x."""
        self.assertTrue(self.code_mapping_spec["openapi"].startswith("3.0"))

    def test_code_mapping_spec_paths(self):
        """Code mapping spec should have 4 path entries."""
        paths = self.code_mapping_spec["paths"]
        self.assertIn("/codes", paths)
        self.assertIn("/codes/{mapping_type}", paths)
        self.assertIn("/codes/{mapping_type}/{code}", paths)
        self.assertIn("/codes/batch", paths)

    def test_code_mapping_operation_ids(self):
        """Each operation should have a unique operationId."""
        paths = self.code_mapping_spec["paths"]
        op_ids = set()
        for path, methods in paths.items():
            for method, op in methods.items():
                if isinstance(op, dict) and "operationId" in op:
                    op_ids.add(op["operationId"])
        expected = {"listMappingTypes", "listCodesByType", "lookupCode", "batchLookup"}
        self.assertEqual(op_ids, expected)

    def test_payment_spec_version(self):
        """Payment spec should be OpenAPI 3.0.x."""
        self.assertTrue(self.payment_spec["openapi"].startswith("3.0"))

    def test_payment_spec_paths(self):
        """Payment spec should have 3 path entries."""
        paths = self.payment_spec["paths"]
        self.assertIn("/payments/validate", paths)
        self.assertIn("/payments/submit", paths)
        self.assertIn("/payments/status/{payment_id}", paths)

    def test_payment_operation_ids(self):
        """Each operation should have a unique operationId."""
        paths = self.payment_spec["paths"]
        op_ids = set()
        for path, methods in paths.items():
            for method, op in methods.items():
                if isinstance(op, dict) and "operationId" in op:
                    op_ids.add(op["operationId"])
        expected = {"validateInvoice", "submitPayment", "checkPaymentStatus"}
        self.assertEqual(op_ids, expected)

    def test_payment_spec_schemas(self):
        """Payment spec should define 3 component schemas."""
        schemas = self.payment_spec["components"]["schemas"]
        self.assertIn("ValidationResult", schemas)
        self.assertIn("PaymentSubmissionResult", schemas)
        self.assertIn("PaymentRecord", schemas)


# ═══════════════════════════════════════════════════════════════════
# Test 5: Payment Processing — End-to-End Simulation
# ═══════════════════════════════════════════════════════════════════


class TestPaymentSimulation(unittest.TestCase):
    """Test the full payment simulation flow."""

    def test_approved_vendor_payment_flow(self):
        """An approved vendor with valid invoice should succeed."""
        inv = validate_invoice_number("INV-2026-78432")
        amt = validate_amount(13531.25)
        vendor = validate_vendor("ABCIND-001")

        self.assertTrue(inv["valid"])
        self.assertTrue(amt["valid"])
        self.assertTrue(vendor["valid"])
        self.assertLessEqual(13531.25, vendor["maxSinglePayment"])

    def test_unapproved_vendor_rejected(self):
        """Payment for GRNENV-006 (Greenfield) should be rejected."""
        vendor = validate_vendor("GRNENV-006")
        self.assertFalse(vendor["valid"])
        self.assertIn("not on the approved vendor list", vendor["reason"])

    def test_over_budget_vendor_rejected(self):
        """$60,000 payment to DELTCH-002 (max $25,000) should fail."""
        vendor = validate_vendor("DELTCH-002")
        self.assertTrue(vendor["valid"])
        self.assertEqual(vendor["maxSinglePayment"], 25000.00)
        # $60,000 > $25,000 → would be rejected in submit_payment

    def test_all_6_ticket_scenarios(self):
        """
        Validate the expected payment outcome for each of the 6 sample tickets:
        1. ZAVA-2026-00001: Happy path → approved
        2. ZAVA-2026-00002: Hazardous + approved vendor → approved (with flag)
        3. ZAVA-2026-00003: Amount discrepancy → manual review (no payment)
        4. ZAVA-2026-00004: Past due → approved (expedited flag)
        5. ZAVA-2026-00005: International freight → approved
        6. ZAVA-2026-00006: Unapproved vendor → rejected
        """
        # Ticket 1: ABC Industrial Supplies, $13,531.25
        v1 = validate_vendor("ABCIND-001")
        self.assertTrue(v1["valid"])
        self.assertTrue(13531.25 <= v1["maxSinglePayment"])

        # Ticket 2: Delta Chemical Solutions, $1,560.42
        v2 = validate_vendor("DELTCH-002")
        self.assertTrue(v2["valid"])
        self.assertTrue(1560.42 <= v2["maxSinglePayment"])

        # Ticket 3: Pinnacle Precision Parts, $8,248.50
        # Note: This ticket has an amount discrepancy, but vendor IS approved
        v3 = validate_vendor("PINPRE-003")
        self.assertTrue(v3["valid"])

        # Ticket 4: Summit Electrical Corp, $2,692.28
        v4 = validate_vendor("SUMELE-004")
        self.assertTrue(v4["valid"])
        self.assertTrue(2692.28 <= v4["maxSinglePayment"])

        # Ticket 5: Oceanic Freight Logistics, $20,900.00
        v5 = validate_vendor("OCEFRT-005")
        self.assertTrue(v5["valid"])
        self.assertTrue(20900.00 <= v5["maxSinglePayment"])

        # Ticket 6: Greenfield Environmental (NOT approved)
        v6 = validate_vendor("GRNENV-006")
        self.assertFalse(v6["valid"])


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Ensure yaml is available for OpenAPI tests
    try:
        import yaml
    except ImportError:
        print("Installing PyYAML for OpenAPI spec tests...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])

    unittest.main(verbosity=2)
