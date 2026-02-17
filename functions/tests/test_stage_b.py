"""
Phase 6 — Unit tests for Stage B AI Information Processing.

Tests the agent_logic module (pure business logic, no SDK deps)
and validates the function app structure.

Run: python -m pytest functions/tests/test_stage_b.py -v
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════
# Path setup
# ═══════════════════════════════════════════════════════════════════

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_FUNCTIONS_DIR = os.path.normpath(os.path.join(_TESTS_DIR, ".."))
_STAGE_B_DIR = os.path.join(_FUNCTIONS_DIR, "stage_b_ai_processing")

if _STAGE_B_DIR not in sys.path:
    sys.path.insert(0, _STAGE_B_DIR)

from agent_logic import (
    AGENT_NAME,
    AGENT_INSTRUCTIONS,
    VALID_NEXT_ACTIONS,
    VALID_FLAGS,
    build_agent_input,
    parse_agent_response,
    build_fallback_result,
    build_success_result,
)


# ═══════════════════════════════════════════════════════════════════
# Test 1: Agent Instructions Validation
# ═══════════════════════════════════════════════════════════════════


class TestAgentInstructions(unittest.TestCase):
    """Validate agent instructions are well-formed and complete."""

    def test_agent_name_format(self):
        """Agent name should be a valid identifier slug."""
        self.assertEqual(AGENT_NAME, "information-processing-agent")
        self.assertTrue(all(c.isalnum() or c == "-" for c in AGENT_NAME))

    def test_instructions_mention_all_tools(self):
        """Instructions should reference MCP tools and code mapping."""
        lower = AGENT_INSTRUCTIONS.lower()
        self.assertIn("read_ticket", AGENT_INSTRUCTIONS)
        self.assertIn("update_ticket", AGENT_INSTRUCTIONS)
        self.assertIn("code mapping", lower)

    def test_instructions_mention_all_processing_steps(self):
        """Instructions should cover all 5 processing steps."""
        self.assertIn("Step 1", AGENT_INSTRUCTIONS)
        self.assertIn("Step 2", AGENT_INSTRUCTIONS)
        self.assertIn("Step 3", AGENT_INSTRUCTIONS)
        self.assertIn("Step 4", AGENT_INSTRUCTIONS)
        self.assertIn("Step 5", AGENT_INSTRUCTIONS)

    def test_instructions_mention_output_format(self):
        """Instructions should specify the expected JSON output format."""
        self.assertIn("ai_processed", AGENT_INSTRUCTIONS)
        self.assertIn("standardizedCodes", AGENT_INSTRUCTIONS)
        self.assertIn("vendorCode", AGENT_INSTRUCTIONS)
        self.assertIn("productCodes", AGENT_INSTRUCTIONS)
        self.assertIn("departmentCode", AGENT_INSTRUCTIONS)
        self.assertIn("costCenter", AGENT_INSTRUCTIONS)
        self.assertIn("nextAction", AGENT_INSTRUCTIONS)
        self.assertIn("summary", AGENT_INSTRUCTIONS)

    def test_instructions_mention_action_codes(self):
        """Instructions should reference all relevant action conditions."""
        self.assertIn("valid_invoice_all_checks_pass", AGENT_INSTRUCTIONS)
        self.assertIn("vendor_not_approved", AGENT_INSTRUCTIONS)
        self.assertIn("amount_discrepancy_detected", AGENT_INSTRUCTIONS)
        self.assertIn("hazardous_materials_present", AGENT_INSTRUCTIONS)

    def test_valid_next_actions_complete(self):
        """Should include all expected next actions."""
        self.assertIn("invoice_processing", VALID_NEXT_ACTIONS)
        self.assertIn("manual_review", VALID_NEXT_ACTIONS)
        self.assertIn("vendor_approval", VALID_NEXT_ACTIONS)
        self.assertIn("budget_approval", VALID_NEXT_ACTIONS)


# ═══════════════════════════════════════════════════════════════════
# Test 2: Agent Input Builder
# ═══════════════════════════════════════════════════════════════════


class TestAgentInput(unittest.TestCase):
    """Tests for build_agent_input function."""

    def test_input_contains_ticket_id(self):
        """The agent input should contain the ticket ID."""
        result = build_agent_input("ZAVA-2026-00001")
        self.assertIn("ZAVA-2026-00001", result)

    def test_input_mentions_tools(self):
        """The agent input should remind the agent to use its tools."""
        result = build_agent_input("ZAVA-2026-00001")
        self.assertIn("read_ticket", result)
        self.assertIn("update_ticket", result)
        self.assertIn("Code Mapping", result)

    def test_input_includes_timestamp(self):
        """The agent input should include a current timestamp."""
        result = build_agent_input("ZAVA-2026-00001")
        # Should contain an ISO timestamp
        self.assertIn("2026", result)
        self.assertIn("T", result)

    def test_input_for_different_tickets(self):
        """Each ticket should produce a unique input message."""
        input1 = build_agent_input("ZAVA-2026-00001")
        input2 = build_agent_input("ZAVA-2026-00002")
        self.assertNotEqual(input1, input2)
        self.assertIn("ZAVA-2026-00001", input1)
        self.assertIn("ZAVA-2026-00002", input2)


# ═══════════════════════════════════════════════════════════════════
# Test 3: Response Parsing
# ═══════════════════════════════════════════════════════════════════


class TestResponseParsing(unittest.TestCase):
    """Tests for parse_agent_response function."""

    def test_parse_json_with_aiprocessing_key(self):
        """Should parse JSON response with aiProcessing structure."""
        response_text = json.dumps({
            "aiProcessing": {
                "summary": "Invoice from ABC Industrial for valve assemblies totaling $13,531.25.",
                "nextAction": "invoice_processing",
                "standardizedCodes": {
                    "vendorCode": "ABCIND-001",
                    "productCodes": ["ZAVA-VLV-4200-IND-STD", "ZAVA-SK-HP-4200-STD"],
                    "departmentCode": "PROC-MFG-001",
                    "costCenter": "CC-4500",
                },
                "flags": [],
            }
        })
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "invoice_processing")
        self.assertEqual(result["standardized_codes"]["vendorCode"], "ABCIND-001")
        self.assertIn("ZAVA-VLV-4200-IND-STD", result["standardized_codes"]["productCodes"])
        self.assertIn("$13,531.25", result["summary"])

    def test_parse_json_with_flat_structure(self):
        """Should parse JSON response with flat keys (summary, nextAction, etc.)."""
        response_text = json.dumps({
            "summary": "Hazardous chemical invoice from Delta Chemical.",
            "nextAction": "invoice_processing",
            "standardizedCodes": {
                "vendorCode": "DELTCH-002",
                "productCodes": ["ZAVA-CHEM-HCL-500-HAZ"],
            },
            "flags": ["HAZARDOUS"],
        })
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "invoice_processing")
        self.assertEqual(result["flags"], ["HAZARDOUS"])

    def test_parse_json_in_code_block(self):
        """Should extract JSON from markdown code blocks."""
        response_text = '''I have processed the ticket. Here are the results:

```json
{
  "summary": "Invoice processed successfully.",
  "nextAction": "invoice_processing",
  "standardizedCodes": {"vendorCode": "ABCIND-001"},
  "flags": []
}
```

The results have been written to the database.'''
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "invoice_processing")

    def test_parse_success_from_text_indicators(self):
        """Should detect success from textual indicators when no JSON present."""
        response_text = (
            "I have successfully updated ticket ZAVA-2026-00001 with the "
            "AI processing results. The status has been set to ai_processed."
        )
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])

    def test_parse_empty_response(self):
        """Should handle empty response gracefully."""
        result = parse_agent_response("")
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_parse_none_response(self):
        """Should handle None response gracefully."""
        result = parse_agent_response(None)
        self.assertFalse(result["success"])

    def test_parse_preserves_raw_output(self):
        """Should always preserve the raw output text."""
        text = "Some agent output text here"
        result = parse_agent_response(text)
        self.assertEqual(result["raw_output"], text)

    def test_parse_with_next_action_snake_case(self):
        """Should handle both camelCase and snake_case nextAction."""
        response_text = json.dumps({
            "summary": "Test",
            "next_action": "manual_review",
            "standardized_codes": {"vendorCode": "TEST-001"},
        })
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "manual_review")


# ═══════════════════════════════════════════════════════════════════
# Test 4: Fallback Result Builder
# ═══════════════════════════════════════════════════════════════════


class TestFallbackResult(unittest.TestCase):
    """Tests for build_fallback_result and build_success_result."""

    def test_fallback_contains_error_message(self):
        """Fallback should include the error message."""
        result = build_fallback_result("ZAVA-2026-00001", "Agent timed out", 5000)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["aiProcessing"]["status"], "error")
        self.assertEqual(result["aiProcessing"]["errorMessage"], "Agent timed out")
        self.assertEqual(result["aiProcessing"]["processingTimeMs"], 5000)

    def test_fallback_has_agent_metadata(self):
        """Fallback should include agent name and version."""
        result = build_fallback_result("ZAVA-2026-00001", "Error")
        self.assertEqual(result["aiProcessing"]["agentName"], AGENT_NAME)
        self.assertEqual(result["aiProcessing"]["agentVersion"], "1")

    def test_fallback_has_timestamp(self):
        """Fallback should include a completedAt timestamp."""
        result = build_fallback_result("ZAVA-2026-00001", "Error")
        self.assertIsNotNone(result["aiProcessing"]["completedAt"])
        # Should be a valid ISO timestamp
        dt = datetime.fromisoformat(result["aiProcessing"]["completedAt"])
        self.assertIsNotNone(dt)

    def test_success_result_format(self):
        """Success result should have expected shape."""
        result = build_success_result(processing_time_ms=3200)
        self.assertEqual(result["status"], "ai_processed")
        self.assertEqual(result["agentName"], AGENT_NAME)
        self.assertEqual(result["processingTimeMs"], 3200)


# ═══════════════════════════════════════════════════════════════════
# Test 5: Function App Structure
# ═══════════════════════════════════════════════════════════════════


class TestFunctionAppStructure(unittest.TestCase):
    """Validate the Stage B function app has all required files."""

    @classmethod
    def setUpClass(cls):
        cls.stage_b_dir = _STAGE_B_DIR

    def test_function_app_exists(self):
        """function_app.py should exist."""
        self.assertTrue(os.path.isfile(os.path.join(self.stage_b_dir, "function_app.py")))

    def test_agent_logic_exists(self):
        """agent_logic.py should exist."""
        self.assertTrue(os.path.isfile(os.path.join(self.stage_b_dir, "agent_logic.py")))

    def test_host_json_exists(self):
        """host.json should exist with correct extension bundle."""
        path = os.path.join(self.stage_b_dir, "host.json")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r") as f:
            host = json.load(f)
        self.assertIn("extensionBundle", host)
        self.assertEqual(host["extensionBundle"]["id"], "Microsoft.Azure.Functions.ExtensionBundle")

    def test_requirements_txt(self):
        """requirements.txt should include azure-ai-projects 2.x."""
        path = os.path.join(self.stage_b_dir, "requirements.txt")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("azure-ai-projects", content)
        self.assertIn("azure-identity", content)
        self.assertIn("azure-functions", content)
        self.assertIn("azure-cosmos", content)

    def test_local_settings_has_required_vars(self):
        """local.settings.json.example should have all required environment variables."""
        path = os.path.join(self.stage_b_dir, "local.settings.json.example")
        self.assertTrue(os.path.isfile(path), "local.settings.json.example not found")
        with open(path, "r") as f:
            settings = json.load(f)
        values = settings.get("Values", {})
        required = [
            "COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_DATABASE",
            "AI_PROJECT_ENDPOINT", "MODEL_DEPLOYMENT_NAME",
            "MCP_COSMOS_ENDPOINT", "CODE_MAPPING_API_ENDPOINT",
        ]
        for key in required:
            self.assertIn(key, values, f"Missing required env var: {key}")

    def test_openapi_spec_accessible(self):
        """The Code Mapping OpenAPI spec should be accessible from stage_b."""
        spec_path = os.path.normpath(
            os.path.join(self.stage_b_dir, "..", "openapi", "code_mapping_api.yaml")
        )
        self.assertTrue(os.path.isfile(spec_path), f"OpenAPI spec not found at {spec_path}")


# ═══════════════════════════════════════════════════════════════════
# Test 6: Agent Response Parsing — All 6 Ticket Scenarios
# ═══════════════════════════════════════════════════════════════════


class TestScenarioParsing(unittest.TestCase):
    """
    Test parsing agent responses for each of the 6 demo ticket scenarios.
    These simulate what the agent would return for each ticket type.
    """

    def test_scenario_1_happy_path(self):
        """Ticket 1: Happy path → invoice_processing."""
        response = json.dumps({
            "aiProcessing": {
                "summary": (
                    "Invoice from ABC Industrial Supplies for 50 valve assemblies and "
                    "100 seal kits totaling $13,531.25 USD. Standard procurement for "
                    "manufacturing line. Vendor is approved. All product codes validated."
                ),
                "nextAction": "invoice_processing",
                "standardizedCodes": {
                    "vendorCode": "ABCIND-001",
                    "productCodes": ["ZAVA-VLV-4200-IND-STD", "ZAVA-SK-HP-4200-STD"],
                    "departmentCode": "PROC-MFG-001",
                    "costCenter": "CC-4500",
                },
                "flags": [],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "invoice_processing")
        self.assertEqual(len(result["standardized_codes"]["productCodes"]), 2)

    def test_scenario_2_hazardous_materials(self):
        """Ticket 2: Hazardous materials → invoice_processing with HAZARDOUS flag."""
        response = json.dumps({
            "aiProcessing": {
                "summary": (
                    "Urgent invoice from Delta Chemical Solutions for hazardous lab "
                    "reagents totaling $1,560.42. Contains HCl and NaOH solutions. "
                    "Vendor approved with NET-15 terms. Hazardous materials handling required."
                ),
                "nextAction": "invoice_processing",
                "standardizedCodes": {
                    "vendorCode": "DELTCH-002",
                    "productCodes": ["ZAVA-CHEM-HCL-500-HAZ", "ZAVA-CHEM-NAOH-1L-HAZ", "ZAVA-PPE-CHEM-KIT-STD"],
                    "departmentCode": "PROC-LAB-002",
                    "costCenter": "CC-4600",
                },
                "flags": ["HAZARDOUS"],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertIn("HAZARDOUS", result["flags"])

    def test_scenario_3_amount_discrepancy(self):
        """Ticket 3: Amount discrepancy → manual_review."""
        response = json.dumps({
            "aiProcessing": {
                "summary": (
                    "Invoice from Pinnacle Precision Parts for $8,248.50. "
                    "Line item price for precision shaft ($350/unit) exceeds expected range. "
                    "Amount discrepancy detected — flagged for manual review."
                ),
                "nextAction": "manual_review",
                "standardizedCodes": {
                    "vendorCode": "PINPRE-003",
                    "productCodes": ["ZAVA-BRG-6205-2RS-STD", "ZAVA-BRG-6308-ZZ-STD", "ZAVA-SHF-D50-L300-STD"],
                    "departmentCode": "PROC-MFG-001",
                    "costCenter": "CC-4500",
                },
                "flags": ["AMOUNT_DISCREPANCY"],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "manual_review")
        self.assertIn("AMOUNT_DISCREPANCY", result["flags"])

    def test_scenario_4_past_due(self):
        """Ticket 4: Past due → invoice_processing with PAST_DUE flag."""
        response = json.dumps({
            "aiProcessing": {
                "summary": (
                    "Invoice from Summit Electrical Corp for $2,692.28. "
                    "Invoice is past NET-45 due date — flagged for expedited payment."
                ),
                "nextAction": "invoice_processing",
                "standardizedCodes": {
                    "vendorCode": "SUMELE-004",
                    "productCodes": ["ZAVA-MTR-3PH-5HP-STD"],
                    "departmentCode": "PROC-MFG-004",
                    "costCenter": "CC-4800",
                },
                "flags": ["PAST_DUE", "EXPEDITED_PAYMENT"],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertIn("PAST_DUE", result["flags"])

    def test_scenario_5_complex_multiline(self):
        """Ticket 5: Complex multi-line international → invoice_processing."""
        response = json.dumps({
            "aiProcessing": {
                "summary": (
                    "International freight invoice from Oceanic Freight Logistics for "
                    "$20,900.00 across 6 line items. Includes ocean freight, customs, "
                    "insurance, and container handling. Approved vendor."
                ),
                "nextAction": "invoice_processing",
                "standardizedCodes": {
                    "vendorCode": "OCEFRT-005",
                    "productCodes": ["ZAVA-FRT-FCL-40-STD", "ZAVA-FRT-CUSTOMS-STD"],
                    "departmentCode": "OPS-LOG-005",
                    "costCenter": "CC-4900",
                },
                "flags": ["INTERNATIONAL_SHIPMENT"],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "invoice_processing")

    def test_scenario_6_unapproved_vendor(self):
        """Ticket 6: Unapproved vendor → vendor_approval."""
        response = json.dumps({
            "aiProcessing": {
                "summary": (
                    "Invoice from Greenfield Environmental Services for $14,045.44. "
                    "CRITICAL: Vendor is NOT on the approved vendor list. "
                    "Requires vendor approval before payment can proceed."
                ),
                "nextAction": "vendor_approval",
                "standardizedCodes": {
                    "vendorCode": "GRNENV-006",
                    "productCodes": ["ZAVA-ENV-HWCT-Q-STD", "ZAVA-ENV-CWTD-GAL-STD", "ZAVA-ENV-EPA-DOC-STD"],
                    "departmentCode": "OPS-ENV-006",
                    "costCenter": "CC-5000",
                },
                "flags": ["UNAPPROVED_VENDOR"],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertEqual(result["next_action"], "vendor_approval")
        self.assertIn("UNAPPROVED_VENDOR", result["flags"])


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
