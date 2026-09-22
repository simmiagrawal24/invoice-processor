"""Agent state + structured-output schemas for the invoice graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field


class AgentState(TypedDict, total=False):
    pdf_path: str
    raw_text: str
    extract_method: str
    invoice: dict[str, Any]  # serialised Invoice dataclass
    repaired: list[str]
    attempts: int
    po_number: str | None
    po_total: float | None
    match_method: str
    _po_matched: bool
    history: list[dict[str, Any]]
    status: str
    reasons: list[str]
    judge: dict[str, Any]  # judge report
    ai_summary: str | None
    events: Annotated[list[str], operator.add]  # node visit log for the UI trace


class RepairOutput(BaseModel):
    """LLM extraction repair. null = not found; never invent values."""

    invoice_number: str | None = Field(default=None)
    date: str | None = Field(default=None)
    po_ref: str | None = Field(default=None)
    vendor: str | None = Field(default=None)
    total: float | None = Field(default=None)
    tax: float | None = Field(default=None)


class JudgeOutput(BaseModel):
    """LLM-as-judge scoring of extraction accuracy."""

    extraction_accuracy: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="")
    suspect_fields: list[str] = Field(default_factory=list)


class SummaryOutput(BaseModel):
    note: str = Field(default="")
