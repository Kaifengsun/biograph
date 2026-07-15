---
goal: Build a frozen 60-query dual-annotator regulatory text retrieval pack
version: 1.0
date_created: 2026-07-15
last_updated: 2026-07-15
owner: Kaifeng Sun
status: 'In progress'
tags: [data, annotation, information-retrieval, reproducibility]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Create one coordinator workbook and six blinded reviewer workbooks for 60 new non-graph regulatory text queries, split into three batches of 20 for an author annotator and an external domain annotator.

## 1. Requirements & Constraints

- **REQ-001**: Produce exactly 60 primary queries in three batches of 20.
- **REQ-002**: Match the locked slice distribution in the approved design specification.
- **REQ-003**: Verify zero identifier and normalized-text overlap with every prior evaluation query.
- **REQ-004**: Include only frozen source chunks as evidence candidates.
- **REQ-005**: Produce A/B workbooks with equal candidate sets and different deterministic orders.
- **CON-001**: Do not include graph nodes, generated answers, summaries, or HyDE text as evidence.
- **CON-002**: Do not inspect reviewer labels until all six completed files are returned.
- **SEC-001**: Do not publish source-bearing review workbooks to GitHub.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build and freeze the query and candidate registry.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Load frozen source chunks and all prior query registries. | | |
| TASK-002 | Create and validate 60 source-grounded questions with the required slice distribution. | | |
| TASK-003 | Build method-balanced evidence pools and blind identifiers. | | |
| TASK-004 | Freeze code, configuration, query registry, candidate registry, Git commit, and SHA-256 values before workbook delivery. | | |

### Implementation Phase 2

- GOAL-002: Generate and verify reviewer artifacts.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Generate the coordinator workbook. | | |
| TASK-006 | Generate Reviewer A batches 01-03 and Reviewer B batches 01-03. | | |
| TASK-007 | Inspect key workbook ranges, data validations, and blinded fields. | | |
| TASK-008 | Render every workbook sheet and visually verify readability. | | |
| TASK-009 | Commit only protocol, code, anonymized registry metadata, and hashes; exclude source-bearing workbooks. | | |

## 3. Alternatives

- **ALT-001**: Use one shared workbook. Rejected because reviewers could see one another's labels.
- **ALT-002**: Use only the existing 30-query confirmatory set. Rejected because it does not expand the evaluation population.
- **ALT-003**: Treat Codex as the second annotator. Rejected because it is neither human nor independent from pack construction.

## 4. Dependencies

- **DEP-001**: `docs/superpowers/specs/2026-07-15-dual-annotator-60-query-design.md`.
- **DEP-002**: Frozen source corpus under `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4/`.
- **DEP-003**: Prior evaluation registries under `data/eval/`.
- **DEP-004**: Bundled `@oai/artifact-tool` runtime.

## 5. Files

- **FILE-001**: `tools/dual_annotation_60/prepare_dual_annotation_pack.py`.
- **FILE-002**: `tools/dual_annotation_60/build_dual_annotation_workbooks.mjs`.
- **FILE-003**: Frozen registry and manifest under `data/eval/dual_annotation_60/`.
- **FILE-004**: Seven user-facing workbooks under `outputs/dual_annotation_60_2026-07-15/`.

## 6. Testing

- **TEST-001**: Assert exact slice and batch counts.
- **TEST-002**: Assert zero prior-query overlap.
- **TEST-003**: Assert candidate IDs exist in the frozen corpus and are unique per query.
- **TEST-004**: Assert no method names, ranks, scores, or real chunk IDs appear in reviewer files.
- **TEST-005**: Assert A/B candidate sets match and order differs.
- **TEST-006**: Scan workbooks for formula errors and render all sheets.

## 7. Risks & Assumptions

- **RISK-001**: Source-grounded question creation may preserve lexical overlap and favor BM25.
- **RISK-002**: Candidate pooling may miss relevant passages outside the initial pool.
- **RISK-003**: The author annotator is not an external independent expert.
- **ASSUMPTION-001**: Reviewer B has the domain background described by the user and did not participate in system development.
- **ASSUMPTION-002**: Both reviewers will return all three batches before any labels are inspected.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-15-dual-annotator-60-query-design.md`
- `data/eval/annotation_guidelines.md`
