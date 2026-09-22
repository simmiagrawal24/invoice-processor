# Invoice Processing — From PDF to Decision

An AP automation workbench that takes a messy vendor invoice PDF and produces an
**Approved / Flagged / Rejected** decision with visible reasoning — built as a
take-home case study, engineered like production software.

**Live app:** <paste Streamlit Cloud URL> · **Demo video:** <paste Loom URL>

## What it does

Upload any invoice PDF. The system extracts fields, matches the purchase order,
applies tolerance / duplicate / split-PO rules, audits its own work with a judge,
and explains every decision — live, stage by stage.

```
PDF → Extract → Normalise → Match PO → Decide → Judge → (Repair ↺) → Note
```

Two flows, one core: a straight **deterministic** chain, and an **agentic**
LangGraph flow (Gemini) that adds LLM field-repair, a reviewer note, and a
judge that scores the parse, retries fixable misses (bounded), and always
explains failures instead of crashing. No key? Both flows agree exactly —
the AI layer is strictly additive.

## Invoice catalog

17 invoices across 12 vendors, each a different layout × failure mode:

| File | Scenario | Result |
|---|---|---|
| `INV-2026-001_happy.pdf` | Clean bill, exact PO match | Approved |
| `INV-2026-002a/b_split.pdf` | One PO split into two milestone bills | Approved, balance → 0 |
| `INV-2026-003_overtolerance.pdf` | Over tolerance, no tax breakdown | Flagged |
| `INV-2026-001_duplicate.pdf` | Same number billed twice | Rejected |
| `INV-2026-004_missing.pdf` | Statement with no invoice number | Rejected |
| `INV-2026-005_bundled.pdf` | Bundled lot, tax embedded | Approved |
| `INV-2026-006_notax.pdf` | No tax line at all | Approved + note |
| `INV-2026-007_implied.pdf` | No PO printed — matched by vendor + amount | Approved (fuzzy) |
| `INV-2026-008_nodate.pdf` | No date anywhere | Approved + note |
| `INV-2026-009_unclear.pdf` | Paragraph items, no total | Rejected |
| `INV-2026-010_close.pdf` | Slightly over tolerance | Flagged |
| `INV-2026-011_wayover.pdf` | Far over PO | Rejected |
| `INV-2026-012_unknown.pdf` | Unknown vendor + unknown PO | Flagged |
| `INV-2026-013_scanned.pdf` | Image-only scan, no text layer | Rejected (OCR if available) |
| `INV-2026-014_splitx.pdf` | Email-style correction, over-billed | Rejected |
| `INV-2026-015_closed.pdf` | Numbered invoice vs closed PO | Rejected |

Try this order: `001` → `002a` → `002b` → `007` → `003` → `012` → `001` again → `013`.

## Run it

```bash
uv sync --dev
uv run streamlit run app.py        # Live Run + Dashboard tabs
```

AI features need one key in `.env` (see `.env.example`):
```
GEMINI_API_KEY=...
```
Visitors can paste their own key in the sidebar (session-only, never stored) —
otherwise runs use the app key, or go fully deterministic with no key at all.

## How it's built

- **Pipeline** (`src/`): `extractor` (pypdf → pdfplumber → OCR) · `normalize`
  (explainable regex; vendors come from procurement data, never code) ·
  `rules` (ordered policy: missing → duplicate → unknown/closed PO → tolerance math with split-PO accounting) · `store` (atomic history)
- **Agent** (`src/agent.py`): LangGraph over the same functions — judge audits
  (deterministic checks + Gemini score), bounded repair loop, structured outputs
- **Quality**: `uv` lockfile, ruff lint+format clean, **36 pytest tests**
  (rule units, 13 end-to-end PDF asserts, offline agent/LLM tests)

## Repo layout

```
app.py  streamlit UI · src/  pipeline+agent · pos.csv  POs
test_invoices/  17 fixtures · tests/  36 tests · generate_test_data.py  fixture builder
```
