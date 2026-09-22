"""Gemini assists for the deterministic path. No key -> silent no-op."""

from __future__ import annotations

import logging

from . import prompts
from .agent_schemas import RepairOutput, SummaryOutput
from .models import get_chat_model, is_agent_configured
from .normalize import Invoice

logger = logging.getLogger(__name__)

_REPAIRABLE = ("invoice_number", "po_ref", "vendor", "total", "tax")


def _structured(model, schema):
    """Accept a chat model (wrap it) or a pre-wrapped/fake runnable (use as-is)."""
    if model is None:
        if not is_agent_configured():
            return None
        model = get_chat_model(temperature=0.0)
    wrap = getattr(model, "with_structured_output", None)
    return wrap(schema) if callable(wrap) else model


def _missing(inv: Invoice) -> list[str]:
    return [f for f in _REPAIRABLE if getattr(inv, f) is None]


def _coerce_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None


def repair_fields(raw_text: str, inv: Invoice, *, model=None) -> tuple[Invoice, list[str]]:
    """Fill regex-missed fields via Gemini. Regex values are never overwritten."""
    missing = _missing(inv)
    structured = _structured(model, RepairOutput) if missing else None
    if structured is None:
        return inv, []
    try:
        out: RepairOutput = structured.invoke(
            [
                ("system", prompts.EXTRACTION_REPAIR_SYSTEM),
                (
                    "user",
                    prompts.EXTRACTION_REPAIR_USER.format(
                        raw_text=raw_text[:4000], missing=", ".join(missing)
                    ),
                ),
            ]
        )
        data = out.model_dump()
    except Exception as exc:  # noqa: BLE001 — repair is best-effort
        logger.warning("gemini repair skipped: %s", type(exc).__name__)
        return inv, []
    repaired: list[str] = []
    updates: dict[str, object] = {}
    for field in missing:
        val = data.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        if field in ("total", "tax"):
            num = _coerce_number(val)
            if num is None:
                continue
            updates[field] = num
        else:
            updates[field] = str(val).strip()
        repaired.append(field)
    if not updates:
        return inv, []
    merged = Invoice(
        invoice_number=updates.get("invoice_number", inv.invoice_number),
        date=inv.date,
        po_ref=updates.get("po_ref", inv.po_ref),
        vendor=updates.get("vendor", inv.vendor),
        total=updates.get("total", inv.total),
        tax=updates.get("tax", inv.tax),
        raw_text=inv.raw_text,
    )
    return merged, repaired


def summarize_decision(
    inv: Invoice, status: str, reasons: list[str], *, model=None, po_total: float | None = None
) -> str | None:
    """Short reviewer note. None when unconfigured or on failure."""
    if model is None and not is_agent_configured():
        return None
    base = model or get_chat_model(temperature=0.2)
    wrap = getattr(base, "with_structured_output", None)
    structured = wrap(SummaryOutput) if callable(wrap) else base
    try:
        out = structured.invoke(
            [
                ("system", prompts.SUMMARY_SYSTEM),
                (
                    "user",
                    prompts.SUMMARY_USER.format(
                        invoice_number=inv.invoice_number or "unknown",
                        vendor=inv.vendor or "unknown vendor",
                        total=f"{inv.total:,.2f}" if inv.total is not None else "unknown",
                        po_number=inv.po_ref or "no PO",
                        po_total=f"{po_total:,.2f}" if po_total is not None else "unknown",
                        status=status,
                        reasons=" | ".join(reasons),
                    ),
                ),
            ]
        )
        text = out.note if hasattr(out, "note") else str(out)
        return text or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("gemini summary skipped: %s", type(exc).__name__)
        return None
