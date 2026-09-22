"""Edge-case tests: split-PO, over-tolerance, end-to-end PDFs."""

from pathlib import Path

import pytest

from src.extractor import extract_text
from src.normalize import Invoice, parse_invoice
from src.pipeline import load_pos
from src.rules import decide, match_po

INV_DIR = Path(__file__).resolve().parent.parent / "test_invoices"


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


def test_split_po_second_invoice_approved():
    """PO-1002 $12k: after 002A ($6k), 002B ($6k) approves with zero remaining."""
    pos = load_pos()
    po, method = match_po("PO-1002", "Globex Systems", 6000.0, pos)
    hist = [
        {
            "po_number": "PO-1002",
            "total": 6000.0,
            "status": "Approved",
            "invoice_number": "INV-2026-002A",
            "run_id": "RUN-001",
            "po_total": 12000.0,
        }
    ]
    inv = make_inv(no="INV-2026-002B", po="PO-1002", total=6000.0, vendor="Globex Systems", tax=0.0)
    d = decide(inv, po, hist, method)
    assert d.status == "Approved"
    assert d.remaining_after == 0.0


def test_overtolerance_flagged():
    """PO-1003 $2750 billed $2900 with no tax -> Flagged, not Rejected."""
    pos = load_pos()
    po, method = match_po("PO-1003", "Initech LLC", 2900.0, pos)
    inv = make_inv(no="INV-2026-003", po="PO-1003", total=2900.0, vendor="Initech LLC", tax=None)
    assert decide(inv, po, [], method).status == "Flagged for review"


@pytest.mark.parametrize(
    ("fname", "exp_inv", "exp_po", "exp_status"),
    [
        ("INV-2026-001_happy.pdf", "INV-2026-001", "PO-1001", "Approved"),
        ("INV-2026-003_overtolerance.pdf", "INV-2026-003", "PO-1003", "Flagged for review"),
        ("INV-2026-004_missing.pdf", None, "PO-1004", "Rejected"),
        ("INV-2026-005_bundled.pdf", "VND-2026-051", "PO-1006", "Approved"),
        ("INV-2026-006_notax.pdf", "HO-2026-118", "PO-1007", "Approved"),
        ("INV-2026-007_implied.pdf", "2026-SI-0441", "PO-1005", "Approved"),
        ("INV-2026-008_nodate.pdf", "WE-6654", "PO-1008", "Approved"),
        ("INV-2026-009_unclear.pdf", "TY-2026-77", "PO-1011", "Rejected"),
        ("INV-2026-010_close.pdf", "CD-2026-309", "PO-1009", "Flagged for review"),
        ("INV-2026-011_wayover.pdf", "SOY-2210", "PO-1010", "Rejected"),
        ("INV-2026-012_unknown.pdf", "GK-8801", "PO-9999", "Flagged for review"),
        ("INV-2026-014_splitx.pdf", "INV-2026-002C", "PO-1002", "Rejected"),
        ("INV-2026-015_closed.pdf", "UMB-2026-310", "PO-1004", "Rejected"),
    ],
)
def test_e2e_pdf_extract_and_decide(fname, exp_inv, exp_po, exp_status):
    """Real PDFs -> extract + parse + decide (no history file writes)."""
    pos = load_pos()
    vendors = [p["vendor"] for p in pos]
    text, method = extract_text(str(INV_DIR / fname))
    assert len(text) > 50, f"no text from {fname} via {method}"
    inv = parse_invoice(text, known_vendors=vendors)
    assert inv.invoice_number == exp_inv
    po, match_method = match_po(inv.po_ref, inv.vendor, inv.total, pos)
    d = decide(inv, po, [], match_method)
    assert d.status == exp_status, f"{fname}: {d.reasons}"
    if exp_po:
        assert (po or {}).get("po_number") or d.po_number == exp_po


def test_missing_date_note():
    """No-date invoice still decides on amounts but carries an advisory reason."""
    pos = load_pos()
    po, method = match_po("PO-1008", "Wayne Enterprises", 4600.0, pos)
    inv = make_inv(no="WE-6654", po="PO-1008", total=4600.0, vendor="Wayne Enterprises")
    inv.date = None
    d = decide(inv, po, [], method)
    assert d.status == "Approved"
    assert any("date" in r.lower() for r in d.reasons)


def test_scanned_pdf_rejected_gracefully(tmp_path, monkeypatch):
    """Image-only scan: no text layer -> clean Rejected, no crash (OCR if tesseract present)."""
    import src.store as store_mod
    from src.pipeline import run

    monkeypatch.setattr(store_mod, "STORE", tmp_path / "history.json")
    out = run(str(INV_DIR / "INV-2026-013_scanned.pdf"))
    assert out["status"] in ("Rejected", "Approved", "Flagged for review")
    if out.get("extract_method") != "ocr":
        assert out["status"] == "Rejected"
