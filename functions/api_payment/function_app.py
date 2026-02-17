"""
Payment Processing REST API — Azure Function (Simulated)

Simulates a payment processing system for Zava Processing Inc.
This API is called by the Invoice Processing Foundry Agent V2 as an
OpenAPI tool via APIM AI Gateway.

Endpoints:
  POST /api/payments/validate     — Validate invoice fields before payment
  POST /api/payments/submit       — Submit invoice for payment
  GET  /api/payments/status/{id}  — Check payment status

Simulation rules:
  • Valid invoices with approved vendors → payment submitted successfully
  • Past-due invoices → flagged for expedited payment
  • Unapproved vendors → payment rejected
  • Amount > vendor-specific limit → payment rejected (per-vendor budget caps)
  • Random small delays to simulate real processing
"""

import json
import logging
import random
from datetime import datetime, timedelta, timezone

import azure.functions as func

from payment_logic import (
    APPROVED_VENDORS,
    validate_invoice_number as _validate_invoice_number,
    validate_amount as _validate_amount,
    validate_due_date as _validate_due_date,
    validate_vendor as _validate_vendor,
)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# In-memory payment ledger (persists for function app lifetime)
# In production, this would be backed by a database.
# ═══════════════════════════════════════════════════════════════════

_payments: dict = {}

# Reference to approved vendors from business logic module
_APPROVED_VENDORS = APPROVED_VENDORS


# ═══════════════════════════════════════════════════════════════════
# POST /api/payments/validate
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="payments/validate",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def validate_invoice(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/payments/validate — Validate invoice fields before payment.

    Request body:
    {
        "invoiceNumber": "INV-2026-78432",
        "vendorCode": "ABCIND-001",
        "amount": 13531.25,
        "dueDate": "2026-02-15",
        "currency": "USD"
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

    invoice_number = body.get("invoiceNumber", "")
    vendor_code = body.get("vendorCode", "")
    amount = body.get("amount", 0)
    due_date = body.get("dueDate", "")
    currency = body.get("currency", "USD")

    # Run all validations
    inv_validation = _validate_invoice_number(invoice_number)
    amt_validation = _validate_amount(amount)
    date_validation = _validate_due_date(due_date) if due_date else {"valid": False, "reason": "Due date is missing"}
    vendor_validation = _validate_vendor(vendor_code)

    # Check vendor budget limit
    budget_valid = True
    budget_reason = ""
    if vendor_validation["valid"] and amount:
        max_payment = vendor_validation.get("maxSinglePayment", float("inf"))
        if amount > max_payment:
            budget_valid = False
            budget_reason = (
                f"Amount ${amount:,.2f} exceeds vendor's max single payment "
                f"of ${max_payment:,.2f}"
            )
        else:
            budget_reason = f"Amount within vendor's payment limit of ${max_payment:,.2f}"

    validations = {
        "invoiceNumberValid": inv_validation["valid"],
        "invoiceNumberDetail": inv_validation["reason"],
        "amountValid": amt_validation["valid"],
        "amountDetail": amt_validation["reason"],
        "dueDateValid": date_validation["valid"],
        "dueDateDetail": date_validation["reason"],
        "vendorApproved": vendor_validation["valid"],
        "vendorDetail": vendor_validation["reason"],
        "budgetAvailable": budget_valid,
        "budgetDetail": budget_reason,
    }

    all_valid = all([
        inv_validation["valid"],
        amt_validation["valid"],
        date_validation["valid"],
        vendor_validation["valid"],
        budget_valid,
    ])

    flags = []
    if date_validation.get("flag"):
        flags.append(date_validation["flag"])
    if date_validation.get("pastDue"):
        flags.append("PAST_DUE")

    result = {
        "invoiceNumber": invoice_number,
        "allValid": all_valid,
        "validations": validations,
        "flags": flags,
        "readyForPayment": all_valid,
        "validatedAt": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Validated invoice %s: allValid=%s", invoice_number, all_valid,
    )

    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json",
        status_code=200,
    )


# ═══════════════════════════════════════════════════════════════════
# POST /api/payments/submit
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="payments/submit",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def submit_payment(req: func.HttpRequest) -> func.HttpResponse:
    """
    POST /api/payments/submit — Submit invoice for payment.

    Request body:
    {
        "invoiceNumber": "INV-2026-78432",
        "vendorCode": "ABCIND-001",
        "vendorName": "ABC Industrial Supplies",
        "amount": 13531.25,
        "currency": "USD",
        "dueDate": "2026-02-15",
        "ticketId": "ZAVA-2026-00001",
        "paymentMethod": "ACH Transfer"
    }

    Simulation rules:
      - Approved vendor + valid amount → success
      - Unapproved vendor → rejected
      - Amount > vendor limit → rejected (budget exceeded)
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            mimetype="application/json",
            status_code=400,
        )

    invoice_number = body.get("invoiceNumber", "")
    vendor_code = body.get("vendorCode", "")
    vendor_name = body.get("vendorName", "")
    amount = body.get("amount", 0)
    currency = body.get("currency", "USD")
    due_date = body.get("dueDate", "")
    ticket_id = body.get("ticketId", "")
    payment_method = body.get("paymentMethod", "ACH Transfer")

    # Validate vendor
    vendor_info = _APPROVED_VENDORS.get(vendor_code)
    if not vendor_info:
        return func.HttpResponse(
            json.dumps({
                "submitted": False,
                "error": f"Payment rejected: vendor '{vendor_code}' is not approved",
                "invoiceNumber": invoice_number,
                "ticketId": ticket_id,
            }),
            mimetype="application/json",
            status_code=200,  # Not a server error, it's a business rejection
        )

    # Check budget
    if amount > vendor_info["maxSinglePayment"]:
        return func.HttpResponse(
            json.dumps({
                "submitted": False,
                "error": (
                    f"Payment rejected: amount ${amount:,.2f} exceeds "
                    f"vendor limit of ${vendor_info['maxSinglePayment']:,.2f}"
                ),
                "invoiceNumber": invoice_number,
                "ticketId": ticket_id,
                "requiredAction": "budget_approval",
            }),
            mimetype="application/json",
            status_code=200,
        )

    # Generate payment ID and simulate submission
    payment_id = f"PAY-{datetime.now(timezone.utc).strftime('%Y')}-{random.randint(10000, 99999)}"
    now = datetime.now(timezone.utc)

    # Simulate expected payment date (3-5 business days before due date, or ASAP if past due)
    try:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
            try:
                due = datetime.strptime(due_date, fmt)
                break
            except ValueError:
                continue
        else:
            due = now + timedelta(days=14)

        if due.replace(tzinfo=None) < now.replace(tzinfo=None):
            expected_payment = now + timedelta(days=1)  # Expedited
        else:
            expected_payment = due - timedelta(days=random.randint(3, 5))
    except Exception:
        expected_payment = now + timedelta(days=7)

    payment_record = {
        "paymentId": payment_id,
        "invoiceNumber": invoice_number,
        "vendorCode": vendor_code,
        "vendorName": vendor_name or vendor_info["name"],
        "amount": amount,
        "currency": currency,
        "ticketId": ticket_id,
        "paymentMethod": payment_method,
        "status": "submitted",
        "submittedAt": now.isoformat(),
        "expectedPaymentDate": expected_payment.strftime("%Y-%m-%d"),
        "dueDate": due_date,
        "approvedBy": "system-auto",
    }

    # Store in memory
    _payments[payment_id] = payment_record

    logger.info(
        "Payment %s submitted for invoice %s (amount: $%s, vendor: %s)",
        payment_id, invoice_number, f"{amount:,.2f}", vendor_code,
    )

    return func.HttpResponse(
        json.dumps({
            "submitted": True,
            "paymentId": payment_id,
            "invoiceNumber": invoice_number,
            "ticketId": ticket_id,
            "amount": amount,
            "currency": currency,
            "paymentMethod": payment_method,
            "status": "submitted",
            "submittedAt": now.isoformat(),
            "expectedPaymentDate": expected_payment.strftime("%Y-%m-%d"),
            "message": f"Payment {payment_id} submitted successfully for ${amount:,.2f}",
        }),
        mimetype="application/json",
        status_code=200,
    )


# ═══════════════════════════════════════════════════════════════════
# GET /api/payments/status/{payment_id}
# ═══════════════════════════════════════════════════════════════════

@app.route(
    route="payments/status/{payment_id}",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def check_payment_status(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/payments/status/{payment_id} — Check payment status.

    Returns the current status of a payment submission.
    Simulates status progression: submitted → processing → completed.
    """
    payment_id = req.route_params.get("payment_id", "")

    if not payment_id:
        return func.HttpResponse(
            json.dumps({"error": "payment_id is required"}),
            mimetype="application/json",
            status_code=400,
        )

    payment = _payments.get(payment_id)
    if not payment:
        return func.HttpResponse(
            json.dumps({"error": f"Payment '{payment_id}' not found"}),
            mimetype="application/json",
            status_code=404,
        )

    # Simulate status progression based on elapsed time
    submitted_at = datetime.fromisoformat(payment["submittedAt"])
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - submitted_at).total_seconds()

    if elapsed_seconds > 120:
        payment["status"] = "completed"
        payment["completedAt"] = (submitted_at + timedelta(seconds=120)).isoformat()
    elif elapsed_seconds > 30:
        payment["status"] = "processing"
    # else: still "submitted"

    return func.HttpResponse(
        json.dumps(payment, default=str),
        mimetype="application/json",
        status_code=200,
    )
