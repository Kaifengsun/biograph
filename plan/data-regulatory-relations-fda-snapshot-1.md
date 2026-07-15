---
goal: Build a provenance-preserving regulatory relation layer and FDA drug-shortage snapshot
version: 1.0
date_created: 2026-07-10
last_updated: 2026-07-10
owner: PharmGraphRAG
status: In progress
tags: [data, regulatory-relations, fda, provenance, graph]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Create a non-destructive extension to the staged regulatory evidence graph. The
extension materializes source-supported document relations and a dated FDA
drug-shortage snapshot without replacing the frozen corpus, existing vector
indexes, or Neo4j database.

## 1. Requirements & Constraints

- **REQ-001**: Read regulatory evidence only from `data/markdown` files whose document ID appears in the frozen 32-document corpus.
- **REQ-002**: Store only explicit, evidence-bearing relations: `COVERS_TOPIC`, `SUPERSEDES`, `COMPLEMENTS`, `USES_PRINCIPLES_FROM`, `APPLIES_DEFINITION_FROM`, `INTERPRETS`, and `REQUIRES_COMPLIANCE_WITH`.
- **REQ-003**: Preserve relation evidence spans, source locators, file hashes, extraction rule IDs, and a graph version on every new edge.
- **REQ-004**: Retrieve all openFDA drug-shortage records from `https://api.fda.gov/drug/shortages.json` with raw API pages and normalized records saved under a date-stamped artifact directory.
- **REQ-005**: Model FDA shortage records separately from existing FDA recall records and never infer recall-to-shortage causality.
- **REQ-006**: Link FDA records to existing drug entities only with exact normalized identifiers or names; retain candidate-match provenance.
- **REQ-007**: Build a new graph artifact directory and refuse an overwrite of any existing output directory.
- **SEC-001**: Use no API keys and write no secrets to artifacts or logs.
- **CON-001**: Do not read `data/chunks`, modify frozen enriched JSON, alter `data/vectors`, or import/delete data in the legacy Neo4j database.
- **CON-002**: Treat FDA API state as a dated snapshot, not a complete historical as-of database.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define deterministic evidence rules and test inputs before data collection.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `extract_regulatory_document_relations.py` with explicit pattern/rule tables, canonical frozen-document validation, deterministic topic/reference node IDs, and evidence-span capture. | Yes | 2026-07-10 |
| TASK-002 | Add `tests/test_regulatory_document_relations.py` covering positive `SUPERSEDES`, `COMPLEMENTS`, `USES_PRINCIPLES_FROM`, and negative bibliography/ambiguous-reference cases. | Yes | 2026-07-10 |
| TASK-003 | Extend `build_regulatory_evidence_graph.py` with optional JSONL attachment inputs and add `extend_graph_snapshot.py` to retain hierarchy-summary nodes while producing a new snapshot only. | Yes | 2026-07-10 |

### Implementation Phase 2

- GOAL-002: Collect and normalize the public FDA drug-shortage source reproducibly.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add `collect_openfda_drug_shortages.py` with paging, retry/backoff, deterministic raw-page filenames, response metadata, SHA-256 hashes, and no-overwrite output behavior. | Yes | 2026-07-10 |
| TASK-005 | Add `normalize_openfda_drug_shortages.py` to emit deterministic event, NDC-product, company, and ingredient JSONL records plus source-derived factual edges. | Yes | 2026-07-10 |
| TASK-006 | Add `tests/test_openfda_drug_shortages.py` for pagination manifests, deterministic IDs, required provenance, and recall/shortage type separation. | Yes | 2026-07-10 |

### Implementation Phase 3

- GOAL-003: Build and audit the combined staged graph extension.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Run the relation extractor against the raw Markdown, inspect its audit report, and build the combined graph artifact with a unique versioned output path. | Yes | 2026-07-10 |
| TASK-008 | Run the FDA collector and normalizer once, then attach its normalized nodes and edges to the combined graph without mutating the raw snapshot. | Yes | 2026-07-10 |
| TASK-009 | Produce `docs/regulatory_relations_fda_snapshot_report_2026-07-10.md` with relation counts, evidence coverage, FDA counts, match coverage, source hashes, limits, and retrieval implications. | Yes | 2026-07-10 |
| TASK-010 | Run the full unit-test suite and preserve command result summaries in the report. | Yes | 2026-07-10 |

## 3. Alternatives

- **ALT-001**: Use an LLM to infer generic `COVERS` and `DEPENDS_ON` edges. Rejected because unsupported semantic edges weaken auditability and create false dependencies.
- **ALT-002**: Use only the existing hand-curated shortage events. Rejected because they lack the public FDA fields and dated provenance needed for reproducible evidence paths.
- **ALT-003**: Replace the legacy Neo4j graph directly. Rejected because it is stale relative to the frozen 2,478-chunk corpus and replacement requires a separate explicit approval.

## 4. Dependencies

- **DEP-001**: Frozen corpus at `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4`.
- **DEP-002**: Raw Markdown at `data/markdown` and document ID mapping from the frozen corpus.
- **DEP-003**: Public `openFDA` Drug Shortages endpoint.
- **DEP-004**: Existing staged graph builder `build_regulatory_evidence_graph.py` and structured entities in `pharma_supply_chain/core_data.py`.

## 5. Files

- **FILE-001**: `docs/superpowers/specs/2026-07-10-regulatory-relations-fda-snapshot-design.md` - approved source/data design.
- **FILE-002**: `extract_regulatory_document_relations.py` - explicit regulatory relation extractor.
- **FILE-003**: `collect_openfda_drug_shortages.py` - public FDA collector.
- **FILE-004**: `normalize_openfda_drug_shortages.py` - snapshot normalizer.
- **FILE-005**: `build_regulatory_evidence_graph.py` - optional staged graph attachment.
- **FILE-006**: `tests/test_regulatory_document_relations.py` - relation extraction tests.
- **FILE-007**: `tests/test_openfda_drug_shortages.py` - snapshot tests.
- **FILE-008**: `artifacts/fda_openfda_drug_shortages/<snapshot_id>/` - raw and normalized FDA snapshot.
- **FILE-009**: `artifacts/regulatory_evidence_graph/<graph_version>/` - combined non-destructive graph snapshot.

## 6. Testing

- **TEST-001**: Every document relation has a matching source span and deterministic source target.
- **TEST-002**: No document relation is emitted from a bibliography-only citation or ambiguous document alias.
- **TEST-003**: All FDA raw pages have manifest entries and SHA-256 hashes.
- **TEST-004**: Normalized FDA node and edge IDs are reproducible from identical raw pages.
- **TEST-005**: No edge mixes `FDA_DrugShortageEvent` and `RecallEvent` event semantics.
- **TEST-006**: The combined graph contains no dangling endpoints and does not overwrite a prior artifact directory.

## 7. Risks & Assumptions

- **RISK-001**: Markdown extraction can contain OCR/text-layout errors; every admitted edge is retained with its literal source span for audit.
- **RISK-002**: openFDA records can be corrected after publication; collection timestamps and raw pages bound reproducibility to the snapshot date.
- **RISK-003**: Generic-name matching can conflate salts, dosage forms, or combination products; exact identifiers are preferred and weak matches remain candidate-only.
- **ASSUMPTION-001**: The public endpoint remains accessible without an API key for the one-time collection volume.
- **ASSUMPTION-002**: Cross-document relations are retrieval aids, not legal interpretations or causal findings.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-10-regulatory-relations-fda-snapshot-design.md`
- `plan/architecture-regulatory-evidence-graph-1.md`
- `docs/regulatory_evidence_graph_snapshot_2026-07-10.md`
- `https://open.fda.gov/apis/drug/drugshortages/`
- `https://open.fda.gov/apis/drug/drugshortages/searchable-fields/`
