"""PO matching + rules engine. Every decision returns reasons (explainable)."""

from dataclasses import dataclass

from .config import FUZZY_TOL_MULT, TOLERANCE_ABS, TOLERANCE_PCT


@dataclass
class Decision:
    status: str  # Approved | Flagged for review | Rejected
    reasons: list[str]
    po_number: str | None
    po_total: float | None
    invoiced_so_far: float
    remaining_after: float | None
    amount_diff: float | None
    match_method: str = "exact"  # exact | fuzzy-vendor | none


def _norm(s: str | None) -> str:
    return (s or "").strip().upper()


def _norm_vendor(s: str | None) -> str:
    # "Acme Supplies Ltd" vs "ACME SUPPLIES LTD" -> equal; strip common suffixes
    v = _norm(s).replace(".", "")
    for suffix in (" LTD", " LLC", " INC", " CORP", " SYSTEMS"):
        if v.endswith(suffix):
            v = v[: -len(suffix)]
    return v.strip()


def match_po(inv_po_ref, inv_vendor, inv_total, pos: list[dict]) -> tuple[dict | None, str]:
    """Returns (po, method). Exact ref first, then fuzzy vendor+amount fallback."""
    if inv_po_ref:
        for po in pos:
            if _norm(po["po_number"]) == _norm(inv_po_ref):
                return po, "exact"
    # Fallback: same vendor (normalised), open POs only, pick closest remaining
    if inv_vendor and inv_total is not None:
        cands = [
            p
            for p in pos
            if _norm_vendor(p.get("vendor")) == _norm_vendor(inv_vendor)
            and p.get("status") != "closed"
        ]
        if len(cands) == 1:
            return cands[0], "fuzzy-vendor"
        if cands:

            def dist(p):
                try:
                    return abs(float(p["po_total"]) - float(inv_total))
                except (ValueError, TypeError):
                    return float("inf")

            best = min(cands, key=dist)
            tol = max(TOLERANCE_ABS, float(inv_total) * TOLERANCE_PCT) * FUZZY_TOL_MULT
            if dist(best) <= tol:
                return best, "fuzzy-vendor"
    return None, "none"


def decide(inv, po: dict | None, history: list[dict], match_method: str = "exact") -> Decision:
    reasons: list[str] = []

    # 1. Missing critical fields
    missing = [
        f
        for f, v in [
            ("invoice_number", inv.invoice_number),
            ("total", inv.total),
        ]
        if v is None
    ]
    if missing:
        return Decision(
            "Rejected",
            [f"Missing critical field(s): {', '.join(missing)} — cannot process."],
            None,
            None,
            0.0,
            None,
            None,
            "none",
        )

    # 2. Duplicate check — normalised (case/whitespace-insensitive)
    inv_id = _norm(inv.invoice_number)
    for h in history:
        if _norm(h.get("invoice_number")) == inv_id and inv_id:
            return Decision(
                "Rejected",
                [f"Duplicate of previous run {h.get('run_id')} (invoice {inv.invoice_number})."],
                h.get("po_number"),
                h.get("po_total"),
                0.0,
                None,
                0.0,
                "exact",
            )

    # 3. PO must exist
    if po is None:
        return Decision(
            "Flagged for review",
            [f"PO reference '{inv.po_ref}' not found in procurement data — needs manual match."],
            inv.po_ref,
            None,
            0.0,
            None,
            None,
            "none",
        )

    if po.get("status") == "closed":
        return Decision(
            "Rejected",
            [f"{po['po_number']} is CLOSED — no further invoices accepted."],
            po["po_number"],
            float(po["po_total"]),
            0.0,
            0.0,
            None,
            match_method,
        )

    if match_method.startswith("fuzzy"):
        reasons.append(
            f"PO matched by vendor fallback ({inv.vendor} → {po['po_number']}) — verify manually if flagged."
        )

    # 4. Split-PO accounting: sum prior approved/flagged against this PO
    invoiced = sum(
        float(h.get("total", 0))
        for h in history
        if h.get("po_number") == po["po_number"]
        and h.get("status") in ("Approved", "Flagged for review")
    )
    po_total = float(po["po_total"])
    remaining = round(po_total - invoiced, 2)
    diff = round(float(inv.total) - remaining, 2)

    tol = max(TOLERANCE_ABS, round(remaining * TOLERANCE_PCT, 2))
    remaining_after = round(remaining - float(inv.total), 2)
    if inv.date is None:
        reasons.append(
            "No invoice date found — amounts checked, confirm the billing period manually."
        )

    if abs(diff) <= tol:
        reasons.append(
            f"Total ${inv.total:,.2f} matches {po['po_number']} remaining ${remaining:,.2f} within tolerance ±${tol:,.2f}."
        )
        if inv.tax is None:
            reasons.append("Note: tax not itemised separately — treated as embedded.")
        if remaining_after > 0.01:
            reasons.append(
                f"Partial billing: ${remaining_after:,.2f} remains on {po['po_number']} (split-PO OK)."
            )
        return Decision(
            "Approved",
            reasons,
            po["po_number"],
            po_total,
            invoiced,
            remaining_after,
            diff,
            match_method,
        )

    if diff > 0 and diff <= tol * FUZZY_TOL_MULT:
        reasons.append(
            f"Total ${inv.total:,.2f} exceeds remaining ${remaining:,.2f} by ${diff:,.2f} — just over tolerance (±${tol:,.2f})."
        )
        if inv.tax is None:
            reasons.append("Tax breakdown missing — cannot verify overage.")
        return Decision(
            "Flagged for review",
            reasons,
            po["po_number"],
            po_total,
            invoiced,
            remaining_after,
            diff,
            match_method,
        )

    if diff > 0:
        reasons.append(
            f"Total ${inv.total:,.2f} exceeds remaining ${remaining:,.2f} by ${diff:,.2f} — over tolerance."
        )
        return Decision(
            "Rejected",
            reasons,
            po["po_number"],
            po_total,
            invoiced,
            remaining_after,
            diff,
            match_method,
        )

    reasons.append(
        f"Total ${inv.total:,.2f} is ${abs(diff):,.2f} under remaining ${remaining:,.2f} — accepted as partial/under-bill."
    )
    return Decision(
        "Approved",
        reasons,
        po["po_number"],
        po_total,
        invoiced,
        remaining_after,
        diff,
        match_method,
    )
