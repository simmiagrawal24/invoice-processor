"""Agent graph tests — fake LangChain runnables, no keys, no network."""

from langchain_core.runnables import RunnableLambda

from src.agent import build_graph, run_agent
from src.agent_schemas import JudgeOutput, RepairOutput, SummaryOutput

PDF = "test_invoices/INV-2026-001_happy.pdf"


def _repair(data):
    return RunnableLambda(lambda messages: RepairOutput(**data))


def _judge(score=1.0, rationale="clean", suspect=()):
    return RunnableLambda(
        lambda messages: JudgeOutput(
            extraction_accuracy=score, rationale=rationale, suspect_fields=list(suspect)
        )
    )


def _summary(note="Reviewer note."):
    return RunnableLambda(lambda messages: SummaryOutput(note=note))


def test_deterministic_agent_matches_pipeline():
    """No models -> same decisions as pipeline.run on representative PDFs."""
    from src.pipeline import run as run_sync

    for fname in (
        "INV-2026-001_happy.pdf",
        "INV-2026-007_implied.pdf",
        "INV-2026-012_unknown.pdf",
        "INV-2026-009_unclear.pdf",
    ):
        import pathlib

        pathlib.Path("runs/history.json").unlink(missing_ok=True)
        expected = run_sync(f"test_invoices/{fname}", use_llm=False)["status"]
        pathlib.Path("runs/history.json").unlink(missing_ok=True)
        got = run_agent(f"test_invoices/{fname}", use_llm=False)
        assert got["status"] == expected, fname
        assert got["judge"]["outcome"] in ("accepted", "needs_attention")
        assert any(t["stage"].startswith("5 · Judge") for t in got["trace"])
    import pathlib

    pathlib.Path("runs/history.json").unlink(missing_ok=True)


def test_accepted_judge_outcome():
    g = build_graph(judge_model=_judge())
    final = g.invoke({"pdf_path": PDF, "attempts": 0, "repaired": []})
    assert final["judge"]["outcome"] == "accepted"
    assert final["judge"]["score"] == 1.0
    assert "judge" in final["events"] and "summarize" in final["events"]


def test_repair_loop_fixes_missing_total(monkeypatch):
    """009 has no total; fake repair supplies it -> judge accepts on retry."""
    import src.agent as agent_mod

    real_parse = agent_mod.parse_invoice

    def parse_no_total(text, **kwargs):
        inv = real_parse(text, **kwargs)
        inv.total = None
        return inv

    monkeypatch.setattr(agent_mod, "parse_invoice", parse_no_total)
    g = build_graph(
        repair_model=_repair({"total": 6300.0}),
        judge_model=_judge(),
        summary_model=_summary(),
    )
    final = g.invoke(
        {"pdf_path": "test_invoices/INV-2026-009_unclear.pdf", "attempts": 0, "repaired": []}
    )
    assert "repair" in final["events"]
    assert final["invoice"]["total"] == 6300.0
    assert final["judge"]["outcome"] == "accepted"
    assert final["ai_summary"] == "Reviewer note."


def test_unfixable_ends_with_reasons():
    """Repair returns junk twice -> stops, outcome explains why."""
    g = build_graph(repair_model=_repair({}), judge_model=_judge())
    final = g.invoke(
        {"pdf_path": "test_invoices/INV-2026-009_unclear.pdf", "attempts": 0, "repaired": []}
    )
    assert final["judge"]["outcome"] == "needs_attention"
    assert "total_present" in final["judge"]["failed"]
    assert "repair exhausted" in final["judge"]["outcome_reason"]
    assert final["judge"]["attempts"] == 2


def test_model_crash_never_breaks_run():
    def boom(messages):
        raise ConnectionError("gemini down")

    from langchain_core.runnables import RunnableLambda

    g = build_graph(
        repair_model=RunnableLambda(boom),
        judge_model=RunnableLambda(boom),
        summary_model=RunnableLambda(boom),
    )
    final = g.invoke({"pdf_path": PDF, "attempts": 0, "repaired": []})
    assert final["status"] == "Approved"  # deterministic core stands
    assert final["judge"]["outcome"] in ("accepted", "needs_attention")


def test_run_agent_result_shape():
    import pathlib

    pathlib.Path("runs/history.json").unlink(missing_ok=True)
    out = run_agent(PDF, judge_model=_judge(0.9, "looks right"), use_llm=True)
    assert out["status"] == "Approved"
    assert out["judge"]["llm_score"] == 0.9
    assert any(t["stage"].startswith("5 · Judge") for t in out["trace"])
    pathlib.Path("runs/history.json").unlink(missing_ok=True)
