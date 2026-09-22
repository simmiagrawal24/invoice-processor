"""Unit tests: parsing + rules engine."""

from src.normalize import Invoice, parse_invoice
from src.rules import decide, match_po

POS = [
    {
        "po_number": "PO-1001",
        "vendor": "Acme Supplies Ltd",
        "po_total": "5000.00",
        "status": "open",
    },
    {"po_number": "PO-1002", "vendor": "Globex Systems", "po_total": "12000.00", "status": "open"},
    {"po_number": "PO-1004", "vendor": "Umbrella Corp", "po_total": "8400.00", "status": "closed"},
]


def make_inv(no="INV-1", po="PO-1001", total=5000.0, vendor="Acme Supplies Ltd", tax=400.0):
    return Invoice(
        invoice_number=no,
        date="2026-09-10",
        po_ref=po,
        vendor=vendor,
        total=total,
        tax=tax,
        raw_text="",
    )


def test_happy_approved():
    po, method = match_po("PO-1001", "Acme", 5000.0, POS)
    assert po["po_number"] == "PO-1001"
    assert decide(make_inv(), po, [], method).status == "Approved"


def test_duplicate_case_insensitive():
    hist = [
        {
            "invoice_number": " inv-1 ",
            "run_id": "RUN-001",
            "po_number": "PO-1001",
            "po_total": 5000.0,
        }
    ]
    po, method = match_po("PO-1001", "Acme", 5000.0, POS)
    assert decide(make_inv(no="INV-1"), po, hist, method).status == "Rejected"


def test_closed_po_rejected():
    po, method = match_po("PO-1004", "Umbrella", 100.0, POS)
    inv = make_inv(no="INV-9", po="PO-1004", total=100.0, vendor="Umbrella Corp")
    assert decide(inv, po, [], method).status == "Rejected"


def test_fuzzy_vendor_match():
    po, method = match_po("PO-9999", "Acme Supplies", 5000.0, POS)
    assert po is not None
    assert method == "fuzzy-vendor"


def test_missing_total_rejected():
    po, method = match_po("PO-1001", "Acme", None, POS)
    assert decide(make_inv(total=None), po, [], method).status == "Rejected"


def test_parse():
    inv = parse_invoice(
        "Vendor: Acme\nInvoice Number: INV-2026-001\nPO Number: PO-1001\nGrand Total: $5,000.00"
    )
    assert inv.invoice_number == "INV-2026-001"
    assert inv.total == 5000.0
