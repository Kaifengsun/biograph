---
goal: Query-routed source-chunk reranking for regulatory evidence retrieval
version: 1.0
date_created: 2026-07-15
last_updated: 2026-07-15
owner: Codex
status: 'In progress'
tags: [feature, retrieval, experiment, paper]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Implement and evaluate a deterministic reranker that combines BM25, raw source-chunk dense retrieval, document hierarchy, and gated graph verification without allowing generated sidecars to occupy evidence ranks.

## 1. Requirements & Constraints

- **REQ-001**: Candidate evidence must contain only frozen source chunk IDs.
- **REQ-002**: BM25 and R1 raw dense retrieval must both contribute candidates.
- **REQ-003**: Query routing and every score contribution must be auditable per query and candidate.
- **REQ-004**: Graph paths must remain separate from text chunk metrics.
- **CON-001**: Tune only on the frozen 60-query development set.
- **CON-002**: Treat the already-observed 30-query ablation set as exploratory validation only; create a new human-confirmed 30-query set for one-time formal evaluation.
- **CON-003**: Do not alter prior formal result artifacts.
- **PAT-001**: Reuse metric and statistical procedures from `evaluate_bm25_enrichment_ablation.py`.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Implement deterministic source-chunk reranking.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add routing, source-only candidate union, feature normalization, score decomposition, and deterministic ranking in `source_chunk_reranker.py`. | ✅ | 2026-07-15 |
| TASK-002 | Add unit tests in `tests/test_source_chunk_reranker.py`. | ✅ | 2026-07-15 |

### Implementation Phase 2

- GOAL-002: Develop and lock the method without held-out access.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Develop the initial routed reranker on 60 queries, diagnose its failure on the observed 30-query set, and select a BM25-default selective table gate on the combined 90 observed queries. | ✅ | 2026-07-15 |
| TASK-004 | Update `lock_source_chunk_reranker.py` and create a final hash-verified method lock for the selective gate. | ✅ | 2026-07-15 |

### Implementation Phase 3

- GOAL-003: Run formal evaluation and update paper assets.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Build and human-review a new 30-query confirmatory pack disjoint from the 60 development and 30 observed validation queries. |  |  |
| TASK-006 | Add and run `evaluate_source_chunk_reranker.py` once on the new frozen confirmatory pack. |  |  |
| TASK-007 | Generate statistical and per-slice paper assets without overwriting prior outputs. |  |  |
| TASK-008 | Update `sections/draft_chinese_rewritten.md` only after results pass validation. |  |  |

## 3. Alternatives

- **ALT-001**: One global BM25-dense weighted score was rejected as insufficiently responsive to query type.
- **ALT-002**: LLM/cross-encoder reranking was deferred because it adds cost, nondeterminism, and model-selection confounding.
- **ALT-003**: Flat RRF over source and generated sidecars was rejected based on the observed candidate-competition failure.

## 4. Dependencies

- **DEP-001**: Frozen enrichment corpus under `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4`.
- **DEP-002**: Frozen FAISS R1 index under `artifacts/retrieval_ablation/deepseek-v4-pro-v4`.
- **DEP-003**: Existing three-path retrieval artifacts for hierarchy and graph audit features.
- **DEP-004**: NumPy, SciPy, statsmodels, and FAISS already used by the project.

## 5. Files

- **FILE-001**: `source_chunk_reranker.py`, new reusable ranking module.
- **FILE-002**: `develop_source_chunk_reranker.py`, development-only parameter selection.
- **FILE-003**: `lock_source_chunk_reranker.py`, immutable method manifest generator.
- **FILE-004**: `evaluate_source_chunk_reranker.py`, formal evaluation entry point.
- **FILE-005**: `tests/test_source_chunk_reranker.py`, focused unit tests.
- **FILE-006**: `sections/draft_chinese_rewritten.md`, result-driven manuscript update.

## 6. Testing

- **TEST-001**: Routing precedence and subtype tests pass.
- **TEST-002**: Candidate union contains unique source chunk IDs only.
- **TEST-003**: Feature normalization and score decomposition are deterministic.
- **TEST-004**: Sidecar aggregation cannot reward duplicate sidecars.
- **TEST-005**: Existing full test suite passes.
- **TEST-006**: Development and held-out artifact integrity checks pass.

## 7. Risks & Assumptions

- **RISK-001**: The 60-query development set may not cover enough paraphrastic semantic queries to tune a robust semantic route.
- **RISK-002**: The 30-query held-out set is small, so slice results are descriptive and confidence intervals may be wide.
- **RISK-003**: Existing three-path retrieval artifacts may not contain raw dense similarity scores; reciprocal-rank features are the deterministic fallback.
- **ASSUMPTION-001**: Frozen corpus and index hashes remain unchanged during the experiment.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-15-source-chunk-reranking-design.md`
- `outputs/bm25_enrichment_ablation_2026-07-15/formal_evaluation.json`
- `outputs/adaptive_text_first_development_2026-07-15-v3/development_report.json`
