"""Agentic invoice flow: LangGraph orchstration over the deterministic core.

Graph: extract → normalize → match → decide → judge ⟳ (repair, ≤N) → summarize → END.

- Every domain step reuses src.extractor / normalize / rules (single source of truth).
- The judge scores the parse + decision deterministically, optionally adds a
  Gemini-as-judge score, routes fixable misses back through LLM repair, and
  always attaches human-readable failure reasons when it cannot be fixed.
- Without a Gemini key the graph still runs: deterministic judge only, no retries.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from . import config, prompts
from .agent_schemas import AgentState, JudgeOutput, RepairOutput, SummaryOutput
from .extractor import extract_text
from .models import get_chat_model, is_configured
from .normalize import Invoice, parse_invoice
from .pipeline import load_pos
from .rules import _norm, decide, match_po
from .store import load as load_history

logger = logging.getLogger(__name__)

_REPAIRABLE = ("invoice_number", "po_ref", "vendor", "total", "tax")


def _to_dict(inv: Invoice) -> dict[str, Any]:
    return {
        "invoice_number": inv.invoice_number,
        "date": inv.date,
        "po_ref": inv.po_ref,
        "vendor": inv.vendor,
        "total": inv.total,
        "tax": inv.tax,
        "raw_text": inv.raw_text,
    }


def _from_dict(d: dict[str, Any]) -> Invoice:
    return Invoice(
        invoice_number=d.get("invoice_number"),
        date=d.get("date"),
        po_ref=d.get("po_ref"),
        vendor=d.get("vendor"),
        total=d.get("total"),
        tax=d.get("tax"),
        raw_text=d.get("raw_text", ""),
    )


def _events(name: str) -> dict[str, list[str]]:
    return {"events": [name]}


# ---------------------------------------------------------------- nodes ---
def n_extract(state: AgentState) -> dict[str, Any]:
    text, method = extract_text(state["pdf_path"])
    return {"raw_text": text, "extract_method": method, **_events("extract")}


def n_normalize(state: AgentState) -> dict[str, Any]:
    vendors = [p["vendor"] for p in load_pos()]
    return {
        "invoice": _to_dict(parse_invoice(state.get("raw_text", ""), known_vendors=vendors)),
        **_events("normalize"),
    }


def _make_repair_node(repair_model):
    def n_repair(state: AgentState) -> dict[str, Any]:
        inv = _from_dict(state["invoice"])
        missing = [f for f in _REPAIRABLE if getattr(inv, f) is None]
        attempts = state.get("attempts", 0) + 1
        if not missing or repair_model is None:
            return {"attempts": attempts, "events": ["repair"]}
        try:
            out: RepairOutput = repair_model.invoke(
                [
                    ("system", prompts.EXTRACTION_REPAIR_SYSTEM),
                    (
                        "user",
                        prompts.EXTRACTION_REPAIR_USER.format(
                            raw_text=inv.raw_text[:4000], missing=", ".join(missing)
                        ),
                    ),
                ]
            )
        except Exception as exc:  # noqa: BLE001 — repair is best-effort
            logger.warning("repair model failed: %s", type(exc).__name__)
            return {"attempts": attempts, "events": ["repair"]}
        data = out.model_dump()
        repaired = list(state.get("repaired", []))
        merged = dict(state["invoice"])
        for field in missing:
            val = data.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            if field in ("total", "tax"):
                try:
                    val = float(str(val).replace(",", "").replace("$", ""))
                except (ValueError, TypeError):
                    continue
            else:
                val = str(val).strip()
            merged[field] = val
            repaired.append(field)
        return {"invoice": merged, "repaired": repaired, "attempts": attempts, "events": ["repair"]}

    return n_repair


def n_match(state: AgentState) -> dict[str, Any]:
    inv = _from_dict(state["invoice"])
    pos = load_pos()
    po, method = match_po(inv.po_ref, inv.vendor, inv.total, pos)
    return {
        "po_number": po["po_number"] if po else inv.po_ref,
        "po_total": float(po["po_total"]) if po else None,
        "match_method": method,
        "_po_matched": bool(po),
        "events": ["match"],
    }


def n_decide(state: AgentState) -> dict[str, Any]:
    inv = _from_dict(state["invoice"])
    pos = load_pos()
    po = next((p for p in pos if p["po_number"] == state.get("po_number")), None)
    if state.get("match_method") == "none":
        po = None
    history = load_history()
    d = decide(inv, po, history, state.get("match_method", "exact"))
    return {
        "status": d.status,
        "reasons": d.reasons,
        "po_number": d.po_number,
        "po_total": d.po_total,
        "history": history,
        "events": ["decide"],
    }


def _deterministic_checks(state: AgentState) -> list[dict[str, Any]]:
    inv = state["invoice"]
    status = state.get("status", "")
    reasons = state.get("reasons", [])
    matched = bool(state.get("_po_matched"))
    method = state.get("match_method", "none")
    history = state.get("history", [])

    checks = [
        {
            "name": "invoice_number_present",
            "passed": bool(inv.get("invoice_number")),
            "detail": f"inv={inv.get('invoice_number')}",
        },
        {
            "name": "total_present",
            "passed": inv.get("total") is not None,
            "detail": f"total={inv.get('total')}",
        },
        {
            "name": "vendor_present",
            "passed": bool(inv.get("vendor")),
            "detail": f"vendor={inv.get('vendor')}",
        },
        {
            "name": "total_positive",
            "passed": (inv.get("total") or 0) > 0,
            "detail": "total must be > 0",
        },
    ]
    if method == "none":
        checks.append(
            {
                "name": "unknown_po_flagged",
                "passed": status == "Flagged for review",
                "detail": f"no PO match; status={status} (must be Flagged)",
            }
        )
    else:
        checks.append(
            {
                "name": "po_resolved",
                "passed": matched,
                "detail": f"po={state.get('po_number')} via {method}",
            }
        )
    if status == "Approved":
        checks.append(
            {
                "name": "approval_supported",
                "passed": matched and inv.get("total") is not None,
                "detail": "approval needs a matched PO and a total",
            }
        )
    elif status == "Rejected" and any("uplicate" in r for r in reasons):
        dup = any(
            _norm(h.get("invoice_number")) == _norm(inv.get("invoice_number")) for h in history
        )
        checks.append(
            {
                "name": "duplicate_verified",
                "passed": dup,
                "detail": "duplicate claim checked against history",
            }
        )
    else:
        checks.append(
            {
                "name": "reasons_present",
                "passed": bool(reasons),
                "detail": f"{len(reasons)} reason(s)",
            }
        )
    return checks


def _fixable_missing(state: AgentState, *, include_po: bool = True) -> list[str]:
    inv = state["invoice"]
    miss = [f for f in ("invoice_number", "total", "vendor") if inv.get(f) is None]
    if (
        include_po
        and state.get("match_method") == "none"
        and inv.get("vendor")
        and inv.get("total") is not None
    ):
        miss.append("po_ref")
    return miss


def _make_judge_node(judge_model):
    def n_judge(state: AgentState) -> dict[str, Any]:
        checks = _deterministic_checks(state)
        failed = [c["name"] for c in checks if not c["passed"]]
        score = sum(1 for c in checks if c["passed"]) / max(len(checks), 1)

        llm_score: float | None = None
        llm_rationale = ""
        llm_suspect: list[str] = []
        if judge_model is not None:
            try:
                out: JudgeOutput = judge_model.invoke(
                    [
                        (
                            "system",
                            "You audit invoice field extraction. Reply with the structured score only.",
                        ),
                        (
                            "user",
                            (
                                f"Extracted: invoice_number={state['invoice'].get('invoice_number')}, "
                                f"date={state['invoice'].get('date')}, po_ref={state['invoice'].get('po_ref')}, "
                                f"vendor={state['invoice'].get('vendor')}, total={state['invoice'].get('total')}, "
                                f"tax={state['invoice'].get('tax')}.\nSource text (truncated):\n{state.get('raw_text', '')[:2000]}"
                            ),
                        ),
                    ]
                )
                llm_score, llm_rationale, llm_suspect = (
                    out.extraction_accuracy,
                    out.rationale,
                    out.suspect_fields,
                )
            except Exception as exc:  # noqa: BLE001 — judge must never crash the run
                logger.warning("judge model failed: %s", type(exc).__name__)
                llm_rationale = (
                    f"LLM judge unavailable ({type(exc).__name__}); deterministic checks only."
                )

        attempts = state.get("attempts", 0)
        fixable = _fixable_missing(state)
        wants_repair = bool(
            failed and fixable and judge_model is not None and attempts < config.AGENT_MAX_REPAIRS
        )

        if not failed:
            outcome, outcome_reason = (
                "accepted",
                "All checks passed — the decision above is correct.",
            )
        elif wants_repair:
            outcome, outcome_reason = (
                "retry",
                f"Failed: {', '.join(failed)}. Fixable: {', '.join(fixable)} (attempt {attempts + 1}).",
            )
        else:
            whys = "; ".join(f"{c['name']}: {c['detail']}" for c in checks if not c["passed"])
            stuck = "no model available" if judge_model is None else "repair exhausted or unfixable"
            outcome, outcome_reason = (
                "needs_attention",
                f"Failed checks — {whys}. ({stuck}; decision stands with reasons.)",
            )

        return {
            "judge": {
                "score": round(score, 3),
                "checks": checks,
                "failed": failed,
                "llm_score": llm_score,
                "llm_rationale": llm_rationale,
                "llm_suspect": llm_suspect,
                "attempts": attempts,
                "outcome": outcome,
                "outcome_reason": outcome_reason,
                "wants_repair": wants_repair,
            },
            "events": ["judge"],
        }

    return n_judge


def _make_summarize_node(summary_model):
    def n_summarize(state: AgentState) -> dict[str, Any]:
        if summary_model is None:
            return {"ai_summary": None, "events": ["summarize"]}
        try:
            out = summary_model.invoke(
                [
                    ("system", prompts.SUMMARY_SYSTEM),
                    (
                        "user",
                        prompts.SUMMARY_USER.format(
                            invoice_number=state["invoice"].get("invoice_number") or "unknown",
                            vendor=state["invoice"].get("vendor") or "unknown vendor",
                            total=f"{state['invoice'].get('total'):,.2f}"
                            if state["invoice"].get("total") is not None
                            else "unknown",
                            po_number=state.get("po_number") or "no PO",
                            po_total=f"{state['po_total']:,.2f}"
                            if state.get("po_total") is not None
                            else "unknown",
                            status=state.get("status", ""),
                            reasons=" | ".join(state.get("reasons", [])),
                        ),
                    ),
                ]
            )
            text = out.note if hasattr(out, "note") else str(out)
            return {"ai_summary": text or None, "events": ["summarize"]}
        except Exception as exc:  # noqa: BLE001
            logger.warning("summary model failed: %s", type(exc).__name__)
            return {"ai_summary": None, "events": ["summarize"]}

    return n_summarize


def _needs_pre_repair(state: AgentState, repair_model) -> bool:
    """Before PO matching, only raw missing fields can justify an LLM repair."""
    if repair_model is None or state.get("attempts", 0) >= config.AGENT_MAX_REPAIRS:
        return False
    inv = state["invoice"]
    return any(inv.get(f) is None for f in ("invoice_number", "total", "vendor"))


def build_graph(*, repair_model=None, judge_model=None, summary_model=None):
    """Assemble the graph. Pass pre-wrapped runnables (real or fakes for tests)."""
    sg = StateGraph(AgentState)
    sg.add_node("extract", n_extract)
    sg.add_node("normalize", n_normalize)
    sg.add_node("repair", _make_repair_node(repair_model))
    sg.add_node("match", n_match)
    sg.add_node("decide", n_decide)
    sg.add_node("judge", _make_judge_node(judge_model))
    sg.add_node("summarize", _make_summarize_node(summary_model))

    sg.set_entry_point("extract")
    sg.add_edge("extract", "normalize")
    sg.add_conditional_edges(
        "normalize", lambda s: "repair" if _needs_pre_repair(s, repair_model) else "match"
    )
    sg.add_edge("repair", "match")
    sg.add_edge("match", "decide")
    sg.add_edge("decide", "judge")
    sg.add_conditional_edges(
        "judge", lambda s: "repair" if s["judge"]["wants_repair"] else "summarize"
    )
    sg.add_edge("summarize", END)
    return sg.compile()


def _default_models(provider=None, api_key=None, model_name=None):
    """Real provider models with structured output, or Nones when unconfigured."""
    provider = provider or config.LLM_PROVIDER
    key = (api_key or "").strip() if api_key else ""
    if not key and not is_configured(provider):
        return None, None, None
    base = get_chat_model(provider, temperature=0.0, api_key=key or None, model=model_name)
    creative = get_chat_model(provider, temperature=0.2, api_key=key or None, model=model_name)
    return (
        base.with_structured_output(RepairOutput),
        base.with_structured_output(JudgeOutput),
        creative.with_structured_output(SummaryOutput),
    )


def run_agent(
    pdf_path: str,
    *,
    repair_model=None,
    judge_model=None,
    summary_model=None,
    use_llm: bool = True,
    provider=None,
    api_key=None,
    model_name=None,
) -> dict:
    """Run the agent graph; returns a pipeline.run-compatible result dict."""
    from .store import save as save_run

    if use_llm and repair_model is None and judge_model is None and summary_model is None:
        repair_model, judge_model, summary_model = _default_models(provider, api_key, model_name)
    graph = build_graph(
        repair_model=repair_model, judge_model=judge_model, summary_model=summary_model
    )
    final: dict = graph.invoke({"pdf_path": pdf_path, "attempts": 0, "repaired": []})

    if not final.get("raw_text"):
        return {
            "status": "Rejected",
            "reasons": [
                "No readable text extracted — scanned image without OCR (install tesseract for OCR)."
            ],
            "trace": [
                {"stage": "1 · Extract", "detail": f"{final.get('extract_method')}: 0 chars"}
            ],
            "judge": {
                "outcome": "needs_attention",
                "outcome_reason": "Nothing to judge — no text extracted.",
                "score": 0.0,
                "checks": [],
                "failed": ["extract_empty"],
                "attempts": 0,
            },
        }

    inv = final["invoice"]
    trace = [
        {
            "stage": "1 · Extract",
            "detail": f"{final.get('extract_method')}: {len(final.get('raw_text', ''))} chars",
        },
        {
            "stage": "2 · Normalise",
            "detail": f"inv={inv.get('invoice_number')} po={inv.get('po_ref')} total={inv.get('total')} tax={inv.get('tax')} vendor={inv.get('vendor')}"
            + (
                f" (AI repaired: {', '.join(final.get('repaired', []))})"
                if final.get("repaired")
                else ""
            ),
        },
        {
            "stage": "3 · Match PO",
            "detail": f"matched {final.get('po_number')} via {final.get('match_method')}"
            if final.get("_po_matched")
            else f"no match for '{inv.get('po_ref')}'",
        },
        {
            "stage": "4 · Rules",
            "detail": f"{final.get('status')}: " + " | ".join(final.get("reasons", [])),
        },
        {
            "stage": "5 · Judge",
            "detail": f"{final['judge']['outcome']} (score {final['judge']['score']}, {final['judge']['attempts']} repairs): {final['judge']['outcome_reason']}",
        },
    ]
    if final.get("ai_summary"):
        trace.append({"stage": "6 · AI note", "detail": final["ai_summary"]})

    entry = {
        "invoice_number": inv.get("invoice_number"),
        "date": inv.get("date"),
        "po_number": final.get("po_number"),
        "po_total": final.get("po_total"),
        "vendor": inv.get("vendor"),
        "total": inv.get("total"),
        "tax": inv.get("tax"),
        "status": final.get("status"),
        "reasons": final.get("reasons", []),
        "extract_method": final.get("extract_method"),
        "match_method": final.get("match_method"),
        "ai_repaired": final.get("repaired", []),
        "ai_summary": final.get("ai_summary"),
        "judge_outcome": final["judge"]["outcome"],
        "judge_score": final["judge"]["score"],
    }
    save_run(entry)
    return {
        **entry,
        "trace": trace,
        "judge": final["judge"],
        "raw_text": final.get("raw_text", "")[:2000],
        "events": final.get("events", []),
    }
