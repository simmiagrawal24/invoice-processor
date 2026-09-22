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

    assert app._session_models("  ") == {}
    models = app._session_models("test-key")
    assert sorted(models) == ["judge_model", "model", "repair_model", "summary_model"]


def test_session_models_bad_key_falls_back(monkeypatch):
    """A key that breaks construction degrades to {} instead of crashing the page."""
    import app

    def boom(**kwargs):
        raise TypeError("bad key format")

    monkeypatch.setattr(app, "get_chat_model", boom)
    assert app._session_models("some-key") == {}


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
