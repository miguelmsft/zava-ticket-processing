"""
Generate professional-looking invoice PDFs for the Zava Processing Inc. demo.

Each PDF simulates a vendor invoice attached to a support ticket.
Uses reportlab for PDF generation.

Usage:
    pip install reportlab
    python generate_sample_pdf.py
"""

import json
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER


# ---------- paths ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TICKETS_PATH = os.path.join(SCRIPT_DIR, "sample_tickets.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "sample_pdfs")


# ---------- styles ----------
def get_styles():
    """Return a dictionary of custom paragraph styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="VendorName",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1a1a2e"),
        fontName="Helvetica-Bold",
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="VendorAddress",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4a4a6a"),
        fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        name="InvoiceTitle",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0078d4"),
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        name="FieldLabel",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#888888"),
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="FieldValue",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1a1a2e"),
        fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        name="FieldValueBold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1a1a2e"),
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader",
        fontSize=10,
        leading=14,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        backColor=colors.HexColor("#0078d4"),
        spaceBefore=12,
        spaceAfter=6,
        leftIndent=4,
    ))
    styles.add(ParagraphStyle(
        name="Footer",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#888888"),
        fontName="Helvetica",
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TotalLabel",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1a1a2e"),
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        name="GrandTotal",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0078d4"),
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    ))
    return styles


def fmt_currency(value: float) -> str:
    """Format a number as USD currency."""
    return f"${value:,.2f}"


def fmt_date(date_str: str) -> str:
    """Format an ISO date string as a human-readable date."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%B %d, %Y")


def build_header(inv: dict, styles: dict) -> list:
    """Build the vendor header + INVOICE title row."""
    elements = []

    # Vendor info (left) + INVOICE title (right)
    vendor_info = [
        [
            Paragraph(inv["vendorName"], styles["VendorName"]),
            Paragraph("INVOICE", styles["InvoiceTitle"]),
        ],
        [
            Paragraph(inv["vendorAddress"], styles["VendorAddress"]),
            "",
        ],
        [
            Paragraph(
                f'Phone: {inv["vendorPhone"]}  |  Email: {inv["vendorEmail"]}',
                styles["VendorAddress"],
            ),
            "",
        ],
    ]

    header_table = Table(vendor_info, colWidths=[4.0 * inch, 3.0 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(
        width="100%", thickness=2,
        color=colors.HexColor("#0078d4"),
        spaceAfter=12,
    ))
    return elements


def build_invoice_details(inv: dict, styles: dict) -> list:
    """Build the invoice number / date / PO / terms detail block."""
    elements = []

    detail_data = [
        [
            Paragraph("INVOICE NUMBER", styles["FieldLabel"]),
            Paragraph("INVOICE DATE", styles["FieldLabel"]),
            Paragraph("DUE DATE", styles["FieldLabel"]),
            Paragraph("PO NUMBER", styles["FieldLabel"]),
        ],
        [
            Paragraph(inv["invoiceNumber"], styles["FieldValueBold"]),
            Paragraph(fmt_date(inv["invoiceDate"]), styles["FieldValue"]),
            Paragraph(fmt_date(inv["dueDate"]), styles["FieldValue"]),
            Paragraph(inv["poNumber"], styles["FieldValue"]),
        ],
    ]
    detail_table = Table(detail_data, colWidths=[1.75 * inch] * 4)
    detail_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    elements.append(detail_table)
    elements.append(Spacer(1, 10))

    # Bill To
    bill_to_data = [
        [
            Paragraph("BILL TO", styles["FieldLabel"]),
            Paragraph("PAYMENT TERMS", styles["FieldLabel"]),
        ],
        [
            Paragraph(inv["billTo"], styles["FieldValue"]),
            Paragraph(inv["paymentTerms"], styles["FieldValueBold"]),
        ],
    ]
    bill_to_table = Table(bill_to_data, colWidths=[5.25 * inch, 1.75 * inch])
    bill_to_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    elements.append(bill_to_table)
    elements.append(Spacer(1, 8))
    return elements


def build_line_items_table(inv: dict, styles: dict) -> list:
    """Build the line items table with alternating row colors."""
    elements = []

    # Table header
    header_row = [
        Paragraph("<b>ITEM</b>", styles["FieldLabel"]),
        Paragraph("<b>PRODUCT CODE</b>", styles["FieldLabel"]),
        Paragraph("<b>QTY</b>", styles["FieldLabel"]),
        Paragraph("<b>UNIT PRICE</b>", styles["FieldLabel"]),
        Paragraph("<b>AMOUNT</b>", styles["FieldLabel"]),
    ]

    table_data = [header_row]

    for idx, item in enumerate(inv["lineItems"]):
        row = [
            Paragraph(item["description"], styles["FieldValue"]),
            Paragraph(item["productCode"], styles["FieldValue"]),
            Paragraph(str(item["quantity"]), styles["FieldValue"]),
            Paragraph(fmt_currency(item["unitPrice"]), styles["FieldValue"]),
            Paragraph(fmt_currency(item["amount"]), styles["FieldValueBold"]),
        ]
        table_data.append(row)

    col_widths = [3.0 * inch, 1.3 * inch, 0.6 * inch, 1.05 * inch, 1.05 * inch]
    line_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Style the table
    table_style = [
        # Header styling
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0078d4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Data rows
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        # Grid
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#0078d4")),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#cccccc")),
        # Alignment
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    # Alternating row colors
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            table_style.append(
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f5f5"))
            )
        # Row separator
        if i < len(table_data) - 1:
            table_style.append(
                ("LINEBELOW", (0, i), (-1, i), 0.5, colors.HexColor("#e0e0e0"))
            )

    line_table.setStyle(TableStyle(table_style))
    elements.append(line_table)
    elements.append(Spacer(1, 12))
    return elements


def build_totals(inv: dict, styles: dict) -> list:
    """Build the subtotal / tax / total block."""
    elements = []

    totals_data = [
        ["", Paragraph("Subtotal:", styles["TotalLabel"]),
         Paragraph(fmt_currency(inv["subtotal"]), styles["FieldValueBold"])],
    ]

    # Optional hazmat surcharge
    if inv.get("hazmatSurcharge"):
        totals_data.append([
            "", Paragraph("Hazmat Surcharge:", styles["TotalLabel"]),
            Paragraph(fmt_currency(inv["hazmatSurcharge"]), styles["FieldValueBold"]),
        ])

    tax_pct = f"{inv['taxRate'] * 100:.2f}%" if inv["taxRate"] > 0 else "Exempt"
    totals_data.append([
        "", Paragraph(f"Tax ({tax_pct}):", styles["TotalLabel"]),
        Paragraph(fmt_currency(inv["taxAmount"]), styles["FieldValueBold"]),
    ])

    totals_data.append([
        "", Paragraph("TOTAL DUE:", styles["GrandTotal"]),
        Paragraph(
            fmt_currency(inv["totalAmount"]),
            ParagraphStyle(
                "GrandTotalValue",
                parent=styles["GrandTotal"],
            ),
        ),
    ])

    totals_table = Table(
        totals_data,
        colWidths=[3.5 * inch, 2.0 * inch, 1.5 * inch],
    )
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (1, -1), (-1, -1), 2, colors.HexColor("#0078d4")),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
    ]))
    elements.append(totals_table)
    return elements


def build_special_notes(inv: dict, styles: dict) -> list:
    """Build any special notes (hazardous flag, BOL, etc.)."""
    elements = []
    notes = []

    if inv.get("hazardousFlag"):
        notes.append(
            f"⚠️  <b>HAZARDOUS MATERIALS:</b> This shipment contains materials "
            f"classified as <b>{inv.get('dotClassification', 'N/A')}</b> under DOT regulations. "
            f"Proper handling procedures must be followed."
        )

    if inv.get("billOfLading"):
        notes.append(
            f"📦  <b>Bill of Lading:</b> {inv['billOfLading']}  |  "
            f"<b>Vessel:</b> {inv.get('vesselName', 'N/A')}  |  "
            f"<b>Voyage:</b> {inv.get('voyageNumber', 'N/A')}"
        )

    if notes:
        elements.append(Spacer(1, 16))
        elements.append(HRFlowable(
            width="100%", thickness=1,
            color=colors.HexColor("#e0e0e0"),
            spaceAfter=8,
        ))
        for note in notes:
            note_style = ParagraphStyle(
                "NoteStyle",
                fontSize=9,
                leading=13,
                textColor=colors.HexColor("#333333"),
                fontName="Helvetica",
                backColor=colors.HexColor("#fff9e6"),
                borderPadding=8,
                spaceBefore=4,
                spaceAfter=4,
            )
            elements.append(Paragraph(note, note_style))

    return elements


def build_footer(inv: dict, styles: dict) -> list:
    """Build the invoice footer with payment instructions."""
    elements = []
    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(
        width="100%", thickness=1,
        color=colors.HexColor("#e0e0e0"),
        spaceAfter=8,
    ))

    footer_text = (
        f"Payment Terms: {inv['paymentTerms']}  |  "
        f"Currency: {inv.get('currency', 'USD')}<br/>"
        f"Please remit payment to {inv['vendorName']}.<br/>"
        f"For billing inquiries, contact {inv['vendorEmail']} or {inv['vendorPhone']}.<br/><br/>"
        f"<i>Thank you for your business!</i>"
    )
    elements.append(Paragraph(footer_text, styles["Footer"]))
    return elements


def generate_invoice_pdf(ticket: dict, output_path: str):
    """Generate a single invoice PDF for a ticket."""
    inv = ticket["invoiceData"]
    styles = get_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    elements = []
    elements.extend(build_header(inv, styles))
    elements.extend(build_invoice_details(inv, styles))
    elements.extend(build_line_items_table(inv, styles))
    elements.extend(build_totals(inv, styles))
    elements.extend(build_special_notes(inv, styles))
    elements.extend(build_footer(inv, styles))

    doc.build(elements)


def main():
    """Generate all sample invoice PDFs."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(TICKETS_PATH, "r", encoding="utf-8") as f:
        tickets = json.load(f)

    print(f"Found {len(tickets)} tickets. Generating PDFs...\n")

    for ticket in tickets:
        filename = ticket["attachmentFilename"]
        output_path = os.path.join(OUTPUT_DIR, filename)
        scenario = ticket.get("scenario", "unknown")

        generate_invoice_pdf(ticket, output_path)
        print(
            f"  ✅ {filename}\n"
            f"     Ticket:   {ticket['ticketId']} — {ticket['title'][:60]}...\n"
            f"     Scenario: {scenario}\n"
            f"     Invoice:  {ticket['invoiceData']['invoiceNumber']} — "
            f"{fmt_currency(ticket['invoiceData']['totalAmount'])}\n"
        )

    print(f"\n🎉 All {len(tickets)} PDFs generated in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
