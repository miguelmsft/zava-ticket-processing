"""
Phase 7 — Unit tests for Stage C Invoice Processing.

Tests the invoice_agent_logic module (pure business logic, no SDK deps)
and validates the function app structure.

Run: python -m pytest functions/tests/test_stage_c.py -v
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
_STAGE_C_DIR = os.path.join(_FUNCTIONS_DIR, "stage_c_invoice_processing")

if _STAGE_C_DIR not in sys.path:
    sys.path.insert(0, _STAGE_C_DIR)

from invoice_agent_logic import (
    AGENT_NAME,
    AGENT_INSTRUCTIONS,
    VALID_INVOICE_STATUSES,
    VALID_PAYMENT_STATUSES,
    build_agent_input,
    parse_agent_response,
    build_fallback_result,
    build_success_result,
)


# ═══════════════════════════════════════════════════════════════════
# Test 1: Agent Instructions Validation
# ═══════════════════════════════════════════════════════════════════


class TestInvoiceAgentInstructions(unittest.TestCase):
    """Validate agent instructions are well-formed and complete."""

    def test_agent_name_format(self):
        """Agent name should be a valid identifier slug."""
        self.assertEqual(AGENT_NAME, "invoice-processing-agent")
        self.assertTrue(all(c.isalnum() or c == "-" for c in AGENT_NAME))

    def test_instructions_mention_all_tools(self):
        """Instructions should reference both MCP and Payment API tools."""
        self.assertIn("read_ticket", AGENT_INSTRUCTIONS)
        self.assertIn("update_ticket", AGENT_INSTRUCTIONS)
        self.assertIn("validate_invoice", AGENT_INSTRUCTIONS)
        self.assertIn("submit_payment", AGENT_INSTRUCTIONS)
        self.assertIn("get_payment_status", AGENT_INSTRUCTIONS)

    def test_instructions_mention_all_processing_steps(self):
        """Instructions should cover all 4 processing steps."""
        self.assertIn("Step 1", AGENT_INSTRUCTIONS)
        self.assertIn("Step 2", AGENT_INSTRUCTIONS)
        self.assertIn("Step 3", AGENT_INSTRUCTIONS)
        self.assertIn("Step 4", AGENT_INSTRUCTIONS)

    def test_instructions_mention_output_format(self):
        """Instructions should specify the expected JSON output format."""
        self.assertIn("invoice_processed", AGENT_INSTRUCTIONS)
        self.assertIn("invoiceProcessing", AGENT_INSTRUCTIONS)
        self.assertIn("validations", AGENT_INSTRUCTIONS)
        self.assertIn("paymentSubmission", AGENT_INSTRUCTIONS)
        self.assertIn("invoiceNumberValid", AGENT_INSTRUCTIONS)
        self.assertIn("amountCorrect", AGENT_INSTRUCTIONS)
        self.assertIn("dueDateValid", AGENT_INSTRUCTIONS)
        self.assertIn("vendorApproved", AGENT_INSTRUCTIONS)
        self.assertIn("budgetAvailable", AGENT_INSTRUCTIONS)

    def test_instructions_mention_validation_fields(self):
        """Instructions should reference Payment API validation fields."""
        self.assertIn("allValid", AGENT_INSTRUCTIONS)
        self.assertIn("readyForPayment", AGENT_INSTRUCTIONS)
        self.assertIn("vendorApproved", AGENT_INSTRUCTIONS)
        self.assertIn("budgetAvailable", AGENT_INSTRUCTIONS)

    def test_instructions_handle_skipped_processing(self):
        """Instructions should cover non-invoice tickets (manual_review, vendor_approval)."""
        self.assertIn("manual_review", AGENT_INSTRUCTIONS)
        self.assertIn("vendor_approval", AGENT_INSTRUCTIONS)
        self.assertIn("budget_approval", AGENT_INSTRUCTIONS)
        self.assertIn("skipped", AGENT_INSTRUCTIONS)

    def test_instructions_mention_payment_fields(self):
        """Instructions should reference payment submission fields."""
        self.assertIn("paymentId", AGENT_INSTRUCTIONS)
        self.assertIn("expectedPaymentDate", AGENT_INSTRUCTIONS)
        self.assertIn("ACH Transfer", AGENT_INSTRUCTIONS)
        self.assertIn("paymentMethod", AGENT_INSTRUCTIONS)

    def test_instructions_have_field_mapping_note(self):
        """Instructions should explicitly map API field names to ticket field names."""
        self.assertIn("Field Name Mapping", AGENT_INSTRUCTIONS)
        self.assertIn("amountValid", AGENT_INSTRUCTIONS)
        self.assertIn("amountCorrect", AGENT_INSTRUCTIONS)
        # The mapping should be directional: API → Ticket
        self.assertIn("API", AGENT_INSTRUCTIONS)
        self.assertIn("Ticket", AGENT_INSTRUCTIONS)

    def test_valid_statuses_complete(self):
        """Should include all expected invoice processing statuses."""
        self.assertIn("completed", VALID_INVOICE_STATUSES)
        self.assertIn("skipped", VALID_INVOICE_STATUSES)
        self.assertIn("error", VALID_INVOICE_STATUSES)
        self.assertIn("submitted", VALID_PAYMENT_STATUSES)
        self.assertIn("rejected", VALID_PAYMENT_STATUSES)
        self.assertIn("not_submitted", VALID_PAYMENT_STATUSES)


# ═══════════════════════════════════════════════════════════════════
# Test 2: Agent Input Builder
# ═══════════════════════════════════════════════════════════════════


class TestInvoiceAgentInput(unittest.TestCase):
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
        self.assertIn("validateInvoice", result)
        self.assertIn("submitPayment", result)

    def test_input_includes_timestamp(self):
        """The agent input should include a current timestamp."""
        result = build_agent_input("ZAVA-2026-00001")
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


class TestInvoiceResponseParsing(unittest.TestCase):
    """Tests for parse_agent_response function."""

    def test_parse_json_with_invoiceprocessing_key(self):
        """Should parse JSON response with invoiceProcessing structure."""
        response_text = json.dumps({
            "invoiceProcessing": {
                "status": "completed",
                "validations": {
                    "invoiceNumberValid": True,
                    "amountCorrect": True,
                    "dueDateValid": True,
                    "vendorApproved": True,
                    "budgetAvailable": True,
                },
                "paymentSubmission": {
                    "submitted": True,
                    "paymentId": "PAY-2026-54321",
                    "submittedAt": "2026-02-06T12:00:00Z",
                    "expectedPaymentDate": "2026-02-10",
                    "paymentMethod": "ACH Transfer",
                },
                "errors": [],
            }
        })
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertEqual(result["payment_id"], "PAY-2026-54321")
        self.assertTrue(result["validations"]["invoiceNumberValid"])
        self.assertEqual(result["errors"], [])

    def test_parse_json_with_flat_payment_submission(self):
        """Should parse JSON response with flat paymentSubmission key."""
        response_text = json.dumps({
            "paymentSubmission": {
                "submitted": True,
                "paymentId": "PAY-2026-11111",
            },
            "validations": {"invoiceNumberValid": True},
            "errors": [],
        })
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertEqual(result["payment_id"], "PAY-2026-11111")

    def test_parse_json_with_validations_only(self):
        """Should handle response with validations but no payment."""
        response_text = json.dumps({
            "validations": {
                "invoiceNumberValid": True,
                "amountCorrect": True,
                "vendorApproved": False,
            },
            "errors": ["Vendor not approved for payment"],
        })
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertFalse(result["payment_submitted"])
        self.assertFalse(result["validations"]["vendorApproved"])
        self.assertEqual(len(result["errors"]), 1)

    def test_parse_json_in_code_block(self):
        """Should extract JSON from markdown code blocks."""
        response_text = '''I have processed the invoice. Here are the results:

```json
{
  "invoiceProcessing": {
    "status": "completed",
    "validations": {"invoiceNumberValid": true, "vendorApproved": true},
    "paymentSubmission": {"submitted": true, "paymentId": "PAY-2026-99999"},
    "errors": []
  }
}
```

The results have been written to the database.'''
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertEqual(result["payment_id"], "PAY-2026-99999")

    def test_parse_success_from_text_indicators(self):
        """Should detect success from textual indicators when no JSON present."""
        response_text = (
            "I have successfully updated ticket ZAVA-2026-00001 with the "
            "invoice processing results. Payment has been submitted with "
            "ID PAY-2026-12345. The status has been set to invoice_processed."
        )
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertEqual(result["payment_id"], "PAY-2026-12345")

    def test_parse_skipped_from_text(self):
        """Should detect skipped processing from text."""
        response_text = (
            "The ticket's nextAction is 'manual_review', not 'invoice_processing'. "
            "I have skipped invoice processing and updated the ticket accordingly."
        )
        result = parse_agent_response(response_text)
        self.assertTrue(result["success"])
        self.assertEqual(result.get("invoice_status"), "skipped")

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


# ═══════════════════════════════════════════════════════════════════
# Test 4: Fallback Result Builder
# ═══════════════════════════════════════════════════════════════════


class TestInvoiceFallbackResult(unittest.TestCase):
    """Tests for build_fallback_result and build_success_result."""

    def test_fallback_contains_error_message(self):
        """Fallback should include the error message."""
        result = build_fallback_result("ZAVA-2026-00001", "Agent timed out", 5000)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["invoiceProcessing"]["status"], "error")
        self.assertEqual(result["invoiceProcessing"]["errorMessage"], "Agent timed out")
        self.assertEqual(result["invoiceProcessing"]["processingTimeMs"], 5000)
        self.assertIn("Agent timed out", result["invoiceProcessing"]["errors"])

    def test_fallback_has_agent_metadata(self):
        """Fallback should include agent name and version."""
        result = build_fallback_result("ZAVA-2026-00001", "Error")
        self.assertEqual(result["invoiceProcessing"]["agentName"], AGENT_NAME)
        self.assertEqual(result["invoiceProcessing"]["agentVersion"], "1")

    def test_fallback_has_null_validations_and_payment(self):
        """Fallback should have null validations and payment."""
        result = build_fallback_result("ZAVA-2026-00001", "Error")
        self.assertIsNone(result["invoiceProcessing"]["validations"])
        self.assertIsNone(result["invoiceProcessing"]["paymentSubmission"])

    def test_fallback_has_timestamp(self):
        """Fallback should include a completedAt timestamp."""
        result = build_fallback_result("ZAVA-2026-00001", "Error")
        self.assertIsNotNone(result["invoiceProcessing"]["completedAt"])
        dt = datetime.fromisoformat(result["invoiceProcessing"]["completedAt"])
        self.assertIsNotNone(dt)

    def test_success_result_format(self):
        """Success result should have expected shape."""
        result = build_success_result(processing_time_ms=4500)
        self.assertEqual(result["status"], "invoice_processed")
        self.assertEqual(result["agentName"], AGENT_NAME)
        self.assertEqual(result["processingTimeMs"], 4500)


# ═══════════════════════════════════════════════════════════════════
# Test 5: Function App Structure
# ═══════════════════════════════════════════════════════════════════


class TestInvoiceFunctionAppStructure(unittest.TestCase):
    """Validate the Stage C function app has all required files."""

    @classmethod
    def setUpClass(cls):
        cls.stage_c_dir = _STAGE_C_DIR

    def test_function_app_exists(self):
        """function_app.py should exist."""
        self.assertTrue(os.path.isfile(os.path.join(self.stage_c_dir, "function_app.py")))

    def test_invoice_agent_logic_exists(self):
        """invoice_agent_logic.py should exist."""
        self.assertTrue(os.path.isfile(os.path.join(self.stage_c_dir, "invoice_agent_logic.py")))

    def test_host_json_exists(self):
        """host.json should exist with correct extension bundle."""
        path = os.path.join(self.stage_c_dir, "host.json")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r") as f:
            host = json.load(f)
        self.assertIn("extensionBundle", host)
        self.assertEqual(host["extensionBundle"]["id"], "Microsoft.Azure.Functions.ExtensionBundle")

    def test_requirements_txt(self):
        """requirements.txt should include azure-ai-projects 2.x."""
        path = os.path.join(self.stage_c_dir, "requirements.txt")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r") as f:
            content = f.read()
        self.assertIn("azure-ai-projects", content)
        self.assertIn("azure-identity", content)
        self.assertIn("azure-functions", content)
        self.assertIn("azure-cosmos", content)

    def test_local_settings_has_required_vars(self):
        """local.settings.json.example should have all required environment variables."""
        path = os.path.join(self.stage_c_dir, "local.settings.json.example")
        self.assertTrue(os.path.isfile(path), "local.settings.json.example not found")
        with open(path, "r") as f:
            settings = json.load(f)
        values = settings.get("Values", {})
        required = [
            "COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_DATABASE",
            "AI_PROJECT_ENDPOINT", "MODEL_DEPLOYMENT_NAME",
            "MCP_COSMOS_ENDPOINT", "PAYMENT_API_ENDPOINT",
        ]
        for key in required:
            self.assertIn(key, values, f"Missing required env var: {key}")

    def test_payment_api_spec_accessible(self):
        """The Payment API OpenAPI spec should be accessible from stage_c."""
        spec_path = os.path.normpath(
            os.path.join(self.stage_c_dir, "..", "openapi", "payment_api.yaml")
        )
        self.assertTrue(os.path.isfile(spec_path), f"OpenAPI spec not found at {spec_path}")


# ═══════════════════════════════════════════════════════════════════
# Test 6: Agent Response Parsing — All 6 Ticket Scenarios
# ═══════════════════════════════════════════════════════════════════


class TestInvoiceScenarioParsing(unittest.TestCase):
    """
    Test parsing agent responses for each of the 6 demo ticket scenarios
    at the invoice processing stage.
    """

    def test_scenario_1_happy_path_payment_submitted(self):
        """Ticket 1: Happy path → payment submitted via ACH Transfer."""
        response = json.dumps({
            "invoiceProcessing": {
                "status": "completed",
                "validations": {
                    "invoiceNumberValid": True,
                    "amountCorrect": True,
                    "dueDateValid": True,
                    "vendorApproved": True,
                    "budgetAvailable": True,
                },
                "paymentSubmission": {
                    "submitted": True,
                    "paymentId": "PAY-2026-54321",
                    "submittedAt": "2026-02-06T12:00:00Z",
                    "expectedPaymentDate": "2026-02-10",
                    "paymentMethod": "ACH Transfer",
                },
                "errors": [],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertTrue(result["payment_id"].startswith("PAY-"))
        self.assertTrue(result["validations"]["invoiceNumberValid"])
        self.assertTrue(result["validations"]["vendorApproved"])
        self.assertEqual(result["errors"], [])

    def test_scenario_2_hazardous_payment_with_flags(self):
        """Ticket 2: Hazardous materials → payment submitted with flags."""
        response = json.dumps({
            "invoiceProcessing": {
                "status": "completed",
                "validations": {
                    "invoiceNumberValid": True,
                    "amountCorrect": True,
                    "dueDateValid": True,
                    "vendorApproved": True,
                    "budgetAvailable": True,
                },
                "paymentSubmission": {
                    "submitted": True,
                    "paymentId": "PAY-2026-54322",
                    "submittedAt": "2026-02-06T12:01:00Z",
                    "expectedPaymentDate": "2026-02-09",
                    "paymentMethod": "ACH Transfer",
                },
                "errors": [],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertEqual(result["errors"], [])

    def test_scenario_3_amount_discrepancy_skipped(self):
        """Ticket 3: Amount discrepancy → nextAction is manual_review, skipped."""
        response = json.dumps({
            "invoiceProcessing": {
                "status": "skipped",
                "validations": None,
                "paymentSubmission": None,
                "errors": [
                    "Ticket nextAction is 'manual_review', not 'invoice_processing'. Skipped."
                ],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertFalse(result["payment_submitted"])
        self.assertEqual(result["invoice_status"], "skipped")
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("manual_review", result["errors"][0])

    def test_scenario_4_past_due_expedited_payment(self):
        """Ticket 4: Past due → payment submitted with expedited flag."""
        response = json.dumps({
            "invoiceProcessing": {
                "status": "completed",
                "validations": {
                    "invoiceNumberValid": True,
                    "amountCorrect": True,
                    "dueDateValid": True,
                    "vendorApproved": True,
                    "budgetAvailable": True,
                },
                "paymentSubmission": {
                    "submitted": True,
                    "paymentId": "PAY-2026-54324",
                    "submittedAt": "2026-02-06T12:02:00Z",
                    "expectedPaymentDate": "2026-02-07",
                    "paymentMethod": "ACH Transfer",
                },
                "errors": [],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertTrue(result["payment_id"].startswith("PAY-"))

    def test_scenario_5_complex_multiline_payment_submitted(self):
        """Ticket 5: Complex multi-line international → payment submitted."""
        response = json.dumps({
            "invoiceProcessing": {
                "status": "completed",
                "validations": {
                    "invoiceNumberValid": True,
                    "amountCorrect": True,
                    "dueDateValid": True,
                    "vendorApproved": True,
                    "budgetAvailable": True,
                },
                "paymentSubmission": {
                    "submitted": True,
                    "paymentId": "PAY-2026-54325",
                    "submittedAt": "2026-02-06T12:03:00Z",
                    "expectedPaymentDate": "2026-02-11",
                    "paymentMethod": "Wire Transfer",
                },
                "errors": [],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertTrue(result["payment_submitted"])
        self.assertEqual(result["errors"], [])

    def test_scenario_6_unapproved_vendor_skipped(self):
        """Ticket 6: Unapproved vendor → nextAction is vendor_approval, skipped."""
        response = json.dumps({
            "invoiceProcessing": {
                "status": "skipped",
                "validations": None,
                "paymentSubmission": None,
                "errors": [
                    "Ticket nextAction is 'vendor_approval', not 'invoice_processing'. Skipped."
                ],
            }
        })
        result = parse_agent_response(response)
        self.assertTrue(result["success"])
        self.assertFalse(result["payment_submitted"])
        self.assertEqual(result["invoice_status"], "skipped")
        self.assertIn("vendor_approval", result["errors"][0])


# ═══════════════════════════════════════════════════════════════════
# Test 7: Payment API OpenAPI Spec Validation
# ═══════════════════════════════════════════════════════════════════


class TestPaymentAPISpecFromStageC(unittest.TestCase):
    """Validate the Payment API OpenAPI spec structure from Stage C perspective."""

    @classmethod
    def setUpClass(cls):
        import yaml

        spec_path = os.path.normpath(
            os.path.join(_STAGE_C_DIR, "..", "openapi", "payment_api.yaml")
        )
        with open(spec_path, "r") as f:
            cls.spec = yaml.safe_load(f)

    def test_spec_has_validate_endpoint(self):
        """Spec should have POST /payments/validate."""
        self.assertIn("/payments/validate", self.spec["paths"])
        self.assertIn("post", self.spec["paths"]["/payments/validate"])

    def test_spec_has_submit_endpoint(self):
        """Spec should have POST /payments/submit."""
        self.assertIn("/payments/submit", self.spec["paths"])
        self.assertIn("post", self.spec["paths"]["/payments/submit"])

    def test_spec_has_status_endpoint(self):
        """Spec should have GET /payments/status/{payment_id}."""
        self.assertIn("/payments/status/{payment_id}", self.spec["paths"])
        self.assertIn("get", self.spec["paths"]["/payments/status/{payment_id}"])

    def test_spec_operation_ids(self):
        """All operation IDs should match what agent instructions reference."""
        validate_op = self.spec["paths"]["/payments/validate"]["post"]
        submit_op = self.spec["paths"]["/payments/submit"]["post"]
        status_op = self.spec["paths"]["/payments/status/{payment_id}"]["get"]

        self.assertEqual(validate_op["operationId"], "validateInvoice")
        self.assertEqual(submit_op["operationId"], "submitPayment")
        self.assertEqual(status_op["operationId"], "checkPaymentStatus")

    def test_spec_schemas_present(self):
        """Component schemas should be defined."""
        schemas = self.spec.get("components", {}).get("schemas", {})
        self.assertIn("ValidationResult", schemas)
        self.assertIn("PaymentSubmissionResult", schemas)
        self.assertIn("PaymentRecord", schemas)


# ═══════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
