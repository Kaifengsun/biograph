---
goal: Implement and lock a deterministic adaptive text-first retrieval policy using only the 60-query development set
version: 1.0
date_created: 2026-07-15
last_updated: 2026-07-15
owner: Codex
status: 'Completed'
tags: [feature, retrieval, experiment, reproducibility]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Implement an auditable post-retrieval policy that prioritizes bottom-up and top-down text evidence, uses explicit document and table signals, gates graph contribution, and prevents rank-5 fusion dilution. Development and parameter selection use only the frozen 60-query development set.

## 1. Requirements & Constraints

- **REQ-001**: Use only `data/eval/three_path_evaluation_frozen_2026-07-15.json` for development and tuning.
- **REQ-002**: Do not read or execute retrieval for the 30-query held-out set during implementation or parameter selection.
- **REQ-003**: Produce deterministic rankings from fixed component rankings, corpus metadata, and explicit parameters.
- **REQ-004**: Treat bottom-up and top-down evidence as primary; graph evidence contributes only after an auditable gate passes.
- **REQ-005**: Record document-routing, table-intent, graph-gate, and route-retention decisions per query.
- **CON-001**: Development Hit@5 must be at least 0.833, the current bottom-up plus top-down RRF baseline.
- **CON-002**: A top-5 text-route candidate must not be removed from the adaptive top 5 unless the replacement has a higher declared confidence tier.
- **CON-003**: Structured FDA nodes remain graph-path validation evidence and never enter text chunk rankings.
- **PAT-001**: Preserve existing retrieval artifacts and add a post-processing module instead of mutating immutable baseline results.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Implement deterministic adaptive ranking primitives.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `adaptive_text_first.py` with weighted RRF, explicit document alias matching, table-intent detection, graph gating, and route-retention scoring. | Yes | 2026-07-15 |
| TASK-002 | Add per-query audit output containing component ranks, applied boosts, graph-gate reason, and final ranking. | Yes | 2026-07-15 |
| TASK-003 | Add unit tests in `tests/test_adaptive_text_first.py` for every gate and invariant. | Yes | 2026-07-15 |

### Implementation Phase 2

- GOAL-002: Select parameters on the 60-query development set and lock the policy.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add `develop_adaptive_text_first.py` to evaluate the declared parameter grid against immutable development retrieval results. | Yes | 2026-07-15 |
| TASK-005 | Select parameters lexicographically by Hit@5, MRR, nDCG@5, fewer graph contributions, then stable parameter order. | Yes | 2026-07-15 |
| TASK-006 | Write the selected parameters and all grid results to `outputs/adaptive_text_first_development_2026-07-15/`. | Yes | 2026-07-15 |

### Implementation Phase 3

- GOAL-003: Lock reproducibility inputs before held-out activation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Run unit tests and the complete repository test suite. | Yes | 2026-07-15 |
| TASK-008 | Write code, corpus, graph, index, development ranking, and parameter hashes to a lock manifest. | Yes | 2026-07-15 |
| TASK-009 | Create a run-ready copy of the frozen 30-query set only after TASK-007 and TASK-008 pass. | Yes | 2026-07-15 |

## 3. Alternatives

- **ALT-001**: Train a learned route classifier on 60 queries. Rejected because sample size is too small and would create avoidable overfitting.
- **ALT-002**: Modify embeddings or regenerate enrichment. Rejected because the current experiment isolates retrieval policy and already has immutable component rankings.
- **ALT-003**: Always fuse all three routes equally. Retained only as a declared baseline because development ablation showed no statistically reliable graph gain.

## 4. Dependencies

- **DEP-001**: Existing `three_path_retrieval.py` component output schema.
- **DEP-002**: Existing `three_path_evaluation.py` metrics.
- **DEP-003**: Immutable development retrieval artifact `artifacts/three_path_retrieval/formal_frozen_2026-07-15/per_query.json`.
- **DEP-004**: Frozen enriched corpus and regulatory graph snapshot.

## 5. Files

- **FILE-001**: `adaptive_text_first.py` - adaptive ranking policy.
- **FILE-002**: `develop_adaptive_text_first.py` - development grid evaluation and lock selection.
- **FILE-003**: `tests/test_adaptive_text_first.py` - deterministic policy tests.
- **FILE-004**: `outputs/adaptive_text_first_development_2026-07-15/` - grid report, per-query audit, and lock manifest.

## 6. Testing

- **TEST-001**: Explicit document aliases boost only matching document chunks.
- **TEST-002**: Table intent boosts table-derived source chunks without admitting summaries as evidence.
- **TEST-003**: Graph fusion abstains without a qualified anchor or structured record.
- **TEST-004**: Structured graph records trigger the graph gate but never enter text rankings.
- **TEST-005**: Route-retention invariant holds at rank 5.
- **TEST-006**: Fixed inputs and parameters produce byte-stable per-query rankings.
- **TEST-007**: Full repository test suite passes.

## 7. Risks & Assumptions

- **RISK-001**: Metadata heuristics may improve development metrics without generalizing; the untouched 30-query run is the only confirmatory result.
- **RISK-002**: Component artifacts store only top-k evidence, limiting reranking of candidates not already retrieved.
- **ASSUMPTION-001**: Existing document IDs, headings, and table markers are stable in the frozen corpus.
- **ASSUMPTION-002**: Fixed FAISS indexes and query embeddings make baseline component rankings deterministic.

## 8. Related Specifications / Further Reading

- `docs/experiments/adaptive_text_first_heldout_protocol_2026-07-15.md`
- `outputs/three_path_evaluation/three_path_ablation_2026-07-15-paper-ready.md`
