"""Field normalisation from raw invoice text. Explainable regex with vendor/format tolerance.

Nothing here names a specific vendor: the approved-vendor list is passed in from
procurement data (pos.csv) by the caller. Without it, vendor detection falls back
to explicit From/Vendor/Billed-By labels only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Invoice:
    invoice_number: str | None
    date: str | None
    po_ref: str | None
    vendor: str | None
    total: float | None
    tax: float | None
    raw_text: str


INV_PATTERNS = [
    re.compile(
        r"invoice\s*(?:number|no\.?|#|id)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/]{2,29})", re.I
    ),
    re.compile(r"invoice\s*#\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/]{2,29})", re.I),
]
DATE_PATTERNS = [
    re.compile(
        r"(?:invoice\s*date|dated|issued|statement\s*date|date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
        re.I,
    ),
    re.compile(
        r"(?:invoice\s*date|dated|issued|statement\s*date|date)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        re.I,
    ),
    re.compile(
        r"(?:invoice\s*date|dated|issued|statement\s*date|date)\s*[:\-]?\s*"
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})",
        re.I,
    ),
    re.compile(
        r"(?:invoice\s*date|dated|issued|statement\s*date|date)\s*[:\-]?\s*(\d{1,2}-[A-Za-z]{3}-\d{4})",
        re.I,
    ),
]
PO_PATTERN = re.compile(
    r"(?:P\.?O\.?\s*(?:number|no\.?|ref|#)?|purchase\s*order|reference|client\s*PO)\s*[:\-/]?\s*(PO[-\s]?\d{3,6})",
    re.I,
)
PO_BARE = re.compile(r"\b(PO[-\s]?\d{3,6})\b", re.I)
TOTAL_LABEL = re.compile(
    r"(?:grand\s*total|balance\s*due|amount\s*(?:due|payable)|total\s*payable|total\s*due|(?<!\w)total(?!\w)(?:\s*\(.*?\))?)\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.I,
)
TAX_PATTERN = re.compile(
    r"(?:tax(?:\s*\(.*?\))?|VAT|sales\s*tax)\s*(?:amount)?\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})", re.I
)
VENDOR_LABEL = re.compile(r"(?:vendor|from|billed\s*by)\s*[:\-]?\s*(.+)", re.I)


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find_invoice_number(text: str) -> str | None:
    for pat in INV_PATTERNS:
        m = pat.search(text)
        if m:
            cand = m.group(1).strip().rstrip(".,;:")
            if cand.lower() in ("date", "number", "no", "id") or not re.search(r"\d", cand):
                continue
            return cand
    return None


def _find_date(text: str) -> str | None:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def _find_last(pattern: re.Pattern, text: str) -> str | None:
    matches = list(pattern.finditer(text))
    return matches[-1].group(1).strip() if matches else None


def _find_vendor(text: str, known_vendors: list[str] | None = None) -> str | None:
    """Explicit label first; approved-vendor list only canonicalises, never invents."""
    known = known_vendors or []
    m = VENDOR_LABEL.search(text)
    if m:
        cand = m.group(1).split("\n")[0].strip().rstrip(".,;")
        for name in known:
            if name.lower() in cand.lower() or cand.lower() in name.lower():
                return name
        if 3 <= len(cand) <= 60 and not re.search(r"[@\d$]{2,}", cand):
            return cand
    lowered = text.lower()
    for name in known:
        if name.lower() in lowered:
            return name
    return None


def _find_tax(text: str) -> float | None:
    # "Tax included where applicable" has no amount -> embedded, not zero
    if re.search(r"tax\s+included", text, re.I) and not TAX_PATTERN.search(text):
        return None
    return _num(_find_last(TAX_PATTERN, text))


def parse_invoice(raw_text: str, known_vendors: list[str] | None = None) -> Invoice:
    po = None
    m = PO_PATTERN.search(raw_text) or PO_BARE.search(raw_text)
    if m:
        po = m.group(1).replace(" ", "").upper()
        if not po.startswith("PO-"):
            po = "PO-" + po[2:].lstrip("- ")

    return Invoice(
        invoice_number=_find_invoice_number(raw_text),
        date=_find_date(raw_text),
        po_ref=po,
        vendor=_find_vendor(raw_text, known_vendors),
        total=_num(_find_last(TOTAL_LABEL, raw_text)),
        tax=_find_tax(raw_text),
        raw_text=raw_text,
    )
