"""Single entry point: PDF -> Decision + trace. Used by Streamlit and CLI."""

import csv
from pathlib import Path

from .assist import repair_fields, summarize_decision
from .extractor import extract_text
from .normalize import parse_invoice
from .rules import decide, match_po
from .store import load, save

BASE = Path(__file__).resolve().parent.parent


def load_pos(path: str | None = None) -> list[dict]:
    p = Path(path) if path else BASE / "pos.csv"
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(pdf_path: str, *, use_llm: bool = True, model=None) -> dict:
    raw_text, method = extract_text(pdf_path)
    stages = [{"stage": "1 · Extract", "detail": f"{method}: {len(raw_text)} chars"}]
    if not raw_text:
        result = {
            "status": "Rejected",
            "reasons": [
                "No readable text extracted — scanned image without OCR (install tesseract for OCR)."
            ],
            "trace": stages,
        }
        return result

    inv = parse_invoice(raw_text, known_vendors=[p["vendor"] for p in load_pos()])
    repaired: list[str] = []
    if use_llm:
        inv, repaired = repair_fields(raw_text, inv, model=model)
    stages.append(
        {
            "stage": "2 · Normalise",
            "detail": f"inv={inv.invoice_number} po={inv.po_ref} total={inv.total} tax={inv.tax} vendor={inv.vendor}"
            + (f" (AI repaired: {', '.join(repaired)})" if repaired else ""),
        }
    )

    pos = load_pos()
    po, match_method = match_po(inv.po_ref, inv.vendor, inv.total, pos)
    stages.append(
        {
            "stage": "3 · Match PO",
            "detail": f"matched {po['po_number']} via {match_method}"
            if po
            else f"no match for '{inv.po_ref}'",
        }
    )

    history = load()
    d = decide(inv, po, history, match_method)
    stages.append({"stage": "4 · Rules", "detail": f"{d.status}: " + " | ".join(d.reasons)})

    ai_summary = (
        summarize_decision(inv, d.status, d.reasons, model=model, po_total=d.po_total)
        if use_llm
        else None
    )
    if ai_summary:
        stages.append({"stage": "5 · AI note", "detail": ai_summary})

    entry = {
        "invoice_number": inv.invoice_number,
        "date": inv.date,
        "po_number": d.po_number,
        "po_total": d.po_total,
        "vendor": inv.vendor,
        "total": inv.total,
        "tax": inv.tax,
        "status": d.status,
        "reasons": d.reasons,
        "extract_method": method,
        "match_method": d.match_method,
        "ai_repaired": repaired,
        "ai_summary": ai_summary,
    }
    save(entry)
    return {**entry, "trace": stages, "raw_text": raw_text[:2000]}
