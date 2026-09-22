"""Invoice → Decision: AP automation workbench. Run with: uv run streamlit run app.py"""

from __future__ import annotations

import tempfile

import pandas as pd
import streamlit as st

from src.agent import run_agent
from src.agent_schemas import JudgeOutput, RepairOutput, SummaryOutput
from src.config import TOLERANCE_ABS, TOLERANCE_PCT
from src.models import default_model, get_chat_model, is_configured
from src.pipeline import load_pos, run
from src.store import load

STATUS_COLOR = {"Approved": "#16a34a", "Flagged for review": "#d97706", "Rejected": "#dc2626"}


def _session_models(provider: str, session_key: str, model_id: str) -> dict:
    """Pre-wrapped provider models bound to a visitor's session key. Never stored.

    Never raises: a bad key must degrade to the app default, not crash the page.
    """
    key = (session_key or "").strip()
    if not key:
        return {}
    try:
        base = get_chat_model(provider, temperature=0.0, api_key=key, model=model_id or None)
        creative = get_chat_model(provider, temperature=0.2, api_key=key, model=model_id or None)
    except Exception as exc:  # noqa: BLE001 — fall back, explain in UI
        import streamlit as st

        st.warning(f"That key didn't work ({type(exc).__name__}) — using the app default instead.")
        return {}
    return {
        "model": base,
        "repair_model": base.with_structured_output(RepairOutput),
        "judge_model": base.with_structured_output(JudgeOutput),
        "summary_model": creative.with_structured_output(SummaryOutput),
    }


st.set_page_config(page_title="AP Workbench · Invoice → Decision", page_icon="🧾", layout="wide")

st.markdown(
    """
    <style>
      .block-container { max-width: 1180px; padding-top: 1.5rem; }
      .kpi { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px 16px; }
      .kpi .v { font-size: 26px; font-weight: 700; margin: 0; }
      .kpi .l { font-size: 12px; color: #6b7280; margin: 0; text-transform: uppercase; letter-spacing: .06em; }
      .verdict { border-radius: 12px; padding: 16px 18px; color: #fff; font-weight: 600; }
      .stage { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; }
      table { font-size: 14px; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 🧾 AP Workbench")
    st.caption("Invoice processing — from PDF to decision")
    st.divider()
    st.markdown("**Procurement data**")
    st.dataframe(pd.DataFrame(load_pos()), width="stretch", hide_index=True)
    st.caption(
        f"Tolerance: ±max(${TOLERANCE_ABS:,.0f}, {TOLERANCE_PCT:.0%}) · Split-PO aware · Duplicate-safe"
    )
    st.divider()
    provider = st.selectbox("Model provider", ["gemini", "openai", "anthropic"], index=0)
    session_key = st.text_input(
        f"Your {provider} key (optional)",
        type="password",
        help="Session-only: overrides the app key for your runs. Never stored — "
        "paste a key from the provider's console.",
    )
    model_id = st.text_input(
        "Model ID",
        value=default_model(provider),
        help="Defaults to the app's model. Any valid ID for the provider works.",
    )
    if session_key.strip():
        st.caption(
            f"🤖 AI runs on **your** key ({provider} / `{model_id or 'default'}`) this session."
        )
    elif is_configured(provider):
        st.markdown(f"**AI assists: ON** 🤖 `{provider}`")
        st.caption("Runs on the app key. Set your own key above to use yours instead.")
    else:
        st.markdown("**AI assists: OFF** — paste a key above to enable")
        st.caption("Repair of missed fields + reviewer note. Core stays deterministic.")
    use_llm = st.checkbox("Use AI assists", value=True)
    mode = st.radio("Flow", ["Deterministic", "Agentic (LangGraph + Gemini)"], index=0)
    if mode.startswith("Agentic") and not (session_key.strip() or is_configured(provider)):
        st.caption("No key for this provider — agent runs with deterministic judge only.")
    if st.button("Reset demo history"):
        from pathlib import Path

        p = Path("runs/history.json")
        if p.exists():
            p.unlink()
        st.rerun()

st.markdown("# Invoice processing — from PDF to decision")
st.caption(
    "Upload a vendor invoice. The pipeline extracts fields, matches the PO, applies tolerance + duplicate + split-PO rules, and explains its decision."
)

hist = load()
c1, c2, c3, c4 = st.columns(4)
total_val = sum(float(h.get("total") or 0) for h in hist)
c1.markdown(
    f"<div class='kpi'><p class='l'>Runs</p><p class='v'>{len(hist)}</p></div>",
    unsafe_allow_html=True,
)
c2.markdown(
    f"<div class='kpi'><p class='l'>Approved</p><p class='v'>{sum(1 for h in hist if h.get('status') == 'Approved')}</p></div>",
    unsafe_allow_html=True,
)
c3.markdown(
    f"<div class='kpi'><p class='l'>Needs review</p><p class='v'>{sum(1 for h in hist if h.get('status') != 'Approved')}</p></div>",
    unsafe_allow_html=True,
)
c4.markdown(
    f"<div class='kpi'><p class='l'>Value processed</p><p class='v'>${total_val:,.0f}</p></div>",
    unsafe_allow_html=True,
)

tab_run, tab_dash = st.tabs(["▶ Live run", "📊 Dashboard"])

with tab_run:
    up = st.file_uploader("Drop an invoice PDF", type=["pdf"])
    if up:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(up.read())
            pdf_path = tmp.name
        agentic = mode.startswith("Agentic")
        session_models = (
            _session_models(provider, session_key, model_id) if session_key.strip() else {}
        )
        with st.status("Running pipeline…", expanded=True) as status:
            st.write("① Extracting text (pypdf → pdfplumber → OCR fallback)")
            st.write("② Normalising fields" + (" + AI repair" if use_llm else ""))
            st.write("③ Matching purchase order")
            st.write("④ Applying AP rules")
            if agentic:
                st.write("⑤ Judge (accuracy audit + repair loop)")
            if use_llm and not agentic:
                st.write("⑤ AI reviewer note")
            if agentic:
                st.write("⑥ AI reviewer note")
            out = None
            try:
                session_key_clean = session_key.strip() or None
                out = (
                    run_agent(
                        pdf_path,
                        use_llm=use_llm,
                        provider=provider,
                        api_key=session_key_clean,
                        model_name=model_id or None,
                        **session_models,
                    )
                    if agentic
                    else run(
                        pdf_path,
                        use_llm=use_llm,
                        model=session_models.get("model"),
                        provider=provider,
                        api_key=session_key_clean,
                        model_name=model_id or None,
                    )
                )
                status.update(label=f"Done — {out['status']}", state="complete")
            except Exception as exc:  # noqa: BLE001 — never show a redacted crash page
                status.update(label="Run failed", state="error")
                st.error(
                    "This invoice couldn't be processed "
                    f"({type(exc).__name__}). Try another file — nothing was saved."
                )
        if out is None:
            st.stop()
        color = STATUS_COLOR.get(out["status"], "#334155")
        st.markdown(
            f"<div class='verdict' style='background:{color}'>{out['status']} · {out.get('invoice_number') or 'no invoice no.'} · ${out.get('total') if out.get('total') is not None else '—'}</div>",
            unsafe_allow_html=True,
        )
        left, right = st.columns([1, 1])
        with left:
            st.subheader("Extracted fields")
            st.table(
                pd.DataFrame(
                    [
                        {
                            "Field": k,
                            "Value": "—" if out.get(k) is None else str(out.get(k)),
                        }
                        for k in (
                            "invoice_number",
                            "date",
                            "po_number",
                            "vendor",
                            "total",
                            "tax",
                            "match_method",
                            "extract_method",
                        )
                    ]
                )
            )
        with right:
            st.subheader("Reasoning")
            for r in out.get("reasons", []):
                st.write("• " + r)
            if out.get("ai_summary"):
                st.subheader("🤖 AI reviewer note")
                st.info(out["ai_summary"])
            elif use_llm and not (session_key.strip() or is_configured(provider)):
                st.caption("AI note skipped — no key for this provider. Core decision unaffected.")
        if out.get("judge"):
            j = out["judge"]
            st.subheader("⚖️ Judge audit")
            st.caption(
                "The judge audits the decision above — not the invoice. “Passed” means the decision is correct, even when the decision is Rejected."
            )
            outcome_label = {
                "accepted": "✅ audit passed",
                "retry": "🔁 retried",
                "needs_attention": "⚠️ needs attention",
            }.get(j.get("outcome"), j.get("outcome"))
            jc1, jc2, jc3 = st.columns(3)
            jc1.metric("Audit", outcome_label)
            jc2.metric("Check score", f"{j.get('score', 0):.0%}")
            jc3.metric("Repair attempts", j.get("attempts", 0))
            st.table(
                pd.DataFrame(
                    [
                        {
                            "Check": c["name"],
                            "Pass": "✅" if c["passed"] else "❌",
                            "Detail": c["detail"],
                        }
                        for c in j.get("checks", [])
                    ]
                )
            )
            if j.get("llm_score") is not None:
                st.caption(
                    f"Gemini extraction accuracy: {j['llm_score']:.2f} — {j.get('llm_rationale', '')}"
                )
                if j.get("llm_suspect"):
                    st.caption("Suspect fields: " + ", ".join(j["llm_suspect"]))
            st.caption(j.get("outcome_reason", ""))
            if out.get("events"):
                st.caption("Agent path: " + " → ".join(out["events"]))
        st.subheader("Stage trace")
        for s in out.get("trace", []):
            st.markdown(
                f"<div class='stage'><b>{s['stage']}</b> — {s['detail']}</div>",
                unsafe_allow_html=True,
            )
        with st.expander("Raw extracted text"):
            st.text(out.get("raw_text", ""))
    else:
        st.info("Upload a PDF from `test_invoices/` — start with `INV-2026-001_happy.pdf`.")

with tab_dash:
    if not hist:
        st.info("No runs yet — process an invoice in Live run.")
    else:
        df = pd.DataFrame(hist)
        f = st.multiselect(
            "Filter status", sorted(df["status"].unique()), default=sorted(df["status"].unique())
        )
        df = df[df["status"].isin(f)]
        st.dataframe(
            df[
                [
                    c
                    for c in (
                        "run_id",
                        "timestamp",
                        "invoice_number",
                        "po_number",
                        "vendor",
                        "total",
                        "status",
                        "match_method",
                    )
                    if c in df.columns
                ]
            ].iloc[::-1],
            width="stretch",
            hide_index=True,
        )
        st.bar_chart(df["status"].value_counts())
        st.download_button(
            "Download history (CSV)", df.to_csv(index=False), "history.csv", "text/csv"
        )
