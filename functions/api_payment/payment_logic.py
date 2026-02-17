"""
Payment Processing — Pure Business Logic

Contains validation functions and reference data that can be imported
without the Azure Functions SDK. Used by both function_app.py (runtime)
and the test suite.
"""

from datetime import datetime, timedelta, timezone

# ═══════════════════════════════════════════════════════════════════
# Approved vendors list (simulation reference data)
# ═══════════════════════════════════════════════════════════════════

APPROVED_VENDORS = {
    "ABCIND-001": {"name": "ABC Industrial Supplies", "maxSinglePayment": 50000.00},
    "DELTCH-002": {"name": "Delta Chemical Solutions", "maxSinglePayment": 25000.00},
    "PINPRE-003": {"name": "Pinnacle Precision Parts", "maxSinglePayment": 30000.00},
    "SUMELE-004": {"name": "Summit Electrical Corp", "maxSinglePayment": 40000.00},
    "OCEFRT-005": {"name": "Oceanic Freight Logistics", "maxSinglePayment": 75000.00},
    # GRNENV-006 intentionally NOT in approved list
}

MAX_SINGLE_PAYMENT = 100_000.00
PAST_DUE_WINDOW_DAYS = 90


def validate_invoice_number(inv_num: str) -> dict:
    """Validate invoice number format: INV-YYYY-NNNNN."""
    if not inv_num:
        return {"valid": False, "reason": "Invoice number is empty"}
    parts = inv_num.split("-")
    if len(parts) != 3 or parts[0] != "INV":
        return {"valid": False, "reason": f"Invalid format: expected INV-YYYY-NNNNN, got '{inv_num}'"}
    if not parts[1].isdigit() or len(parts[1]) != 4:
        return {"valid": False, "reason": f"Invalid year component: '{parts[1]}'"}
    if not parts[2].isdigit():
        return {"valid": False, "reason": f"Invalid sequence number: '{parts[2]}'"}
    return {"valid": True, "reason": "Format valid"}


def validate_amount(amount: float) -> dict:
    """Validate payment amount is within acceptable range."""
    if amount is None or amount <= 0:
        return {"valid": False, "reason": "Amount must be positive"}
    if amount > MAX_SINGLE_PAYMENT:
        return {
            "valid": False,
            "reason": f"Amount ${amount:,.2f} exceeds maximum single payment limit of ${MAX_SINGLE_PAYMENT:,.0f}",
        }
    return {"valid": True, "reason": f"Amount ${amount:,.2f} within acceptable range"}


def validate_due_date(due_date_str: str) -> dict:
    """Validate due date — check if it's a valid date and how far in past/future."""
    try:
        # Accept ISO format and common date formats
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
            try:
                due_date = datetime.strptime(due_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            return {"valid": False, "reason": f"Cannot parse date: '{due_date_str}'"}

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        days_until = (due_date - now).days

        if days_until < -PAST_DUE_WINDOW_DAYS:
            return {
                "valid": False,
                "reason": f"Due date is {abs(days_until)} days past due — exceeds {PAST_DUE_WINDOW_DAYS}-day payment window",
                "pastDue": True,
                "daysOverdue": abs(days_until),
            }
        elif days_until < 0:
            return {
                "valid": True,
                "reason": f"Due date is {abs(days_until)} days past due — flagged for expedited payment",
                "pastDue": True,
                "daysOverdue": abs(days_until),
                "flag": "EXPEDITED_PAYMENT",
            }
        else:
            return {
                "valid": True,
                "reason": f"Due date is {days_until} days from now",
                "pastDue": False,
            }
    except Exception as e:
        return {"valid": False, "reason": f"Date validation error: {str(e)}"}


def validate_vendor(vendor_code: str) -> dict:
    """Validate vendor is on approved list."""
    if not vendor_code:
        return {"valid": False, "reason": "Vendor code is empty"}

    if vendor_code in APPROVED_VENDORS:
        vendor = APPROVED_VENDORS[vendor_code]
        return {
            "valid": True,
            "reason": f"Vendor '{vendor['name']}' is approved",
            "vendorName": vendor["name"],
            "maxSinglePayment": vendor["maxSinglePayment"],
        }
    else:
        return {
            "valid": False,
            "reason": f"Vendor code '{vendor_code}' is not on the approved vendor list",
        }
