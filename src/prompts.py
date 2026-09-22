"""Versioned LLM prompt templates. Bump VERSION when wording changes (cache keys include it)."""

from __future__ import annotations

VERSION = "v1"

EXTRACTION_REPAIR_SYSTEM = """You extract structured fields from invoice text.
Reply with ONLY a JSON object, no prose, no code fences. Keys: invoice_number, date, po_ref, vendor, total, tax.
Use null for anything not present. Totals and tax are numbers (no currency symbols)."""

EXTRACTION_REPAIR_USER = """Invoice text:
---
{raw_text}
---
Known missing fields: {missing}.
Return the JSON object with your best values for ALL keys (null where absent)."""

SUMMARY_SYSTEM = """You write short accounts-payable decision notes for reviewers.
Reply with 2-3 plain sentences: what was billed, how it compares to the PO, and the required next step.
No greeting, no bullet points, no invented numbers — use only the facts given."""

SUMMARY_USER = """Invoice {invoice_number} from {vendor} totals ${total} against {po_number} (PO value ${po_total}).
Decision: {status}. Reasons: {reasons}.
Write the reviewer note."""
