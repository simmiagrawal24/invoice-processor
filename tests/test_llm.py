"""Gemini assist tests — all offline via fake runnables, no key needed."""

import pytest
from langchain_core.runnables import RunnableLambda

from src import config
from src.agent_schemas import RepairOutput, SummaryOutput
from src.assist import repair_fields, summarize_decision
from src.normalize import Invoice


def _inv(**over):
    base = {
        "invoice_number": "INV-9",
        "date": "2026-09-10",
        "po_ref": "PO-1001",
        "vendor": "Acme Supplies Ltd",
        "total": 5000.0,
        "tax": 400.0,
        "raw_text": "",
    }
    base.update(over)
    return Invoice(**base)


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")


def test_noop_without_key(no_key):
    inv, repaired = repair_fields("text", _inv(total=None))
    assert repaired == [] and inv.total is None
    assert summarize_decision(_inv(), "Approved", ["ok"]) is None


def test_repair_fills_only_missing():
    fake = RunnableLambda(lambda m: RepairOutput(total=2900.0, vendor="HACKED"))
    out, repaired = repair_fields("text", _inv(total=None, tax=None), model=fake)
    assert out.total == 2900.0
    assert out.tax is None
    assert out.vendor == "Acme Supplies Ltd"  # regex value never overwritten
    assert repaired == ["total"]


def test_repair_ignores_garbage_numbers():
    fake = RunnableLambda(lambda m: RepairOutput(total="a lot"))
    out, repaired = repair_fields("t", _inv(total=None), model=fake)
    assert repaired == [] and out.total is None


def test_repair_failure_returns_original():
    def boom(messages):
        raise ConnectionError("down")

    out, repaired = repair_fields("t", _inv(total=None), model=RunnableLambda(boom))
    assert repaired == [] and out.total is None


def test_summary_text():
    fake = RunnableLambda(lambda m: SummaryOutput(note="Billed $5k vs PO. Pay it."))
    assert summarize_decision(_inv(), "Approved", ["ok"], model=fake) == "Billed $5k vs PO. Pay it."


def test_session_models_build():
    """The exact UI path: blank -> {}, key -> 4 pre-wrapped models, never raises."""
    import app

    assert app._session_models("gemini", "  ", "") == {}
    models = app._session_models("gemini", "test-key", "")
    assert sorted(models) == ["judge_model", "model", "repair_model", "summary_model"]


def test_agent_kwargs_drops_raw_model():
    """Regression: app passes session dict into run_agent — raw chat model must be stripped."""
    import app

    d = {"model": object(), "repair_model": 1, "judge_model": 2, "summary_model": 3}
    assert app._agent_kwargs(d) == {"repair_model": 1, "judge_model": 2, "summary_model": 3}


def test_run_agent_accepts_app_session_shape():
    """End-to-end with the exact kwarg shape the UI builds (minus raw model)."""
    import pathlib

    from langchain_core.runnables import RunnableLambda

    from src.agent import run_agent
    from src.agent_schemas import JudgeOutput, SummaryOutput

    pathlib.Path("runs/history.json").unlink(missing_ok=True)
    out = run_agent(
        "test_invoices/INV-2026-001_happy.pdf",
        use_llm=True,
        provider="gemini",
        api_key=None,
        model_name=None,
        repair_model=RunnableLambda(lambda m: RepairOutput()),
        judge_model=RunnableLambda(lambda m: JudgeOutput(extraction_accuracy=1.0, rationale="ok")),
        summary_model=RunnableLambda(lambda m: SummaryOutput(note="n")),
    )
    assert out["status"] == "Approved"
    pathlib.Path("runs/history.json").unlink(missing_ok=True)


def test_session_models_bad_key_falls_back(monkeypatch):
    """A key that breaks construction degrades to {} instead of crashing the page."""
    import app

    def boom(**kwargs):
        raise TypeError("bad key format")

    monkeypatch.setattr(app, "get_chat_model", boom)
    assert app._session_models("gemini", "some-key", "") == {}


def test_summary_receives_po_value():
    seen = {}

    def fake(messages):
        seen["user"] = messages[1][1]
        return SummaryOutput(note="note")

    summarize_decision(_inv(), "Approved", ["ok"], model=RunnableLambda(fake), po_total=3200.0)
    assert "PO value $3,200.00" in seen["user"]


def test_summary_failure_is_none():
    def boom(messages):
        raise TimeoutError("slow")

    assert summarize_decision(_inv(), "Approved", ["ok"], model=RunnableLambda(boom)) is None


def test_unknown_provider_rejected():
    from src.models import get_chat_model

    with pytest.raises(RuntimeError, match="Unknown provider"):
        get_chat_model("bedrock")


def test_missing_key_raises():
    from src import config
    from src.models import get_chat_model

    old = config.OPENAI_API_KEY
    config.OPENAI_API_KEY = ""
    try:
        with pytest.raises(RuntimeError, match="No API key"):
            get_chat_model("openai")
    finally:
        config.OPENAI_API_KEY = old


def test_all_providers_construct_offline():
    from src.models import get_chat_model

    assert type(get_chat_model("openai", api_key="x")).__name__ == "ChatOpenAI"
    assert type(get_chat_model("anthropic", api_key="x")).__name__ == "ChatAnthropic"
    assert type(get_chat_model("gemini", api_key="x")).__name__ == "ChatGoogleGenerativeAI"
