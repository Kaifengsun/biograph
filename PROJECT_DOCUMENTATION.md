# BioGraph Project Documentation

## Current scope

BioGraph supports evidence-backed analysis across two data representations:

- a frozen corpus of pharmaceutical regulatory documents organized as
  documents, sections, source chunks, and tables; and
- a frozen evidence graph derived from openFDA drug-shortage records and
  normalized product, ingredient, manufacturer, and provenance entities.

The framework routes an analyst request to text retrieval, structured path
retrieval, or both. Text evidence and graph evidence may be displayed together,
but they remain separate evidence types and are evaluated with separate
criteria.

## Research contribution

The work is positioned as an application and evaluation study in information
retrieval, natural-language processing, and pharmaceutical regulatory science.
Its central design principle is auditability: generated summaries and synthetic
questions may guide retrieval, but final text evidence must point back to frozen
source wording, and graph paths must preserve relation direction and provenance.

The manuscript focuses on three questions:

1. How well can source chunks be retrieved from heterogeneous regulatory text?
2. When do hierarchy-aware navigation and neural reranking help beyond a strong
   lexical baseline?
3. Which structured supply-chain and regulatory relations can be verified with
   deterministic, provenance-backed graph paths?

It does not claim precise shortage-duration forecasting, autonomous regulatory
decision-making, or general state-of-the-art superiority.

## Main modules

### `pharma_doc_pipeline`

Converts source documents, restores hierarchy, creates source chunks and table
records, generates source-grounded retrieval aids, and builds vector indexes.
`main.py` coordinates the pipeline; individual `step_*.py` modules can also be
run independently.

### `pharma_supply_chain`

Collects and normalizes pharmaceutical entities and shortage facts, then builds
the structured graph representation. Connection details are supplied through
environment variables; credentials are not part of the repository.

### `pharma_graphrag`

Contains retrieval components for source chunks, hierarchy navigation, and
bounded graph traversal. The paper's final framing is text-first: graph evidence
is used where the task asks for structured relations or provenance, not as a
replacement for citable regulatory passages.

### `tools`

Contains frozen-set preparation, double-annotation analysis, adjudication,
BM25/enrichment experiments, selective reranking, MedCPT and Qwen3 extensions,
relation-chain ranking, and review-workbook utilities. See
`docs/SCRIPT_INDEX.md` for the maintained entry points.

### `paper`

Contains the English manuscript, bibliography, tables, figures, validation
checks, and Word conversion utilities. `paper/scripts/validate_paper.py` checks
that the reported manuscript values agree with the frozen evaluation artifacts.

## Verification

From the repository root:

```powershell
python -m pytest -q
python paper/scripts/validate_paper.py
```

The test configuration intentionally limits discovery to `tests/`. Historical
or separately maintained local projects are not part of the BioGraph test suite.

## Data and release policy

The working directory retains frozen research assets needed for peer review,
including local corpora, indexes, model files, Neo4j state, and audit records.
They are excluded from Git because of size, licensing, privacy, or
machine-specific paths. A future public data package should include only files
that pass source-licensing, privacy, and redistribution review.

For reproducibility details, use `docs/REPRODUCIBILITY.md`. For the current
scientific narrative and numerical results, the validated manuscript in
`paper/` is authoritative.
