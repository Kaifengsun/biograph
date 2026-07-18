---
goal: Implement and evaluate locked relation-aware graph evidence-chain ranking
version: 1.0
date_created: 2026-07-18
last_updated: 2026-07-18
owner: Sun Kaifeng
status: 'In progress'
tags: [feature, experiment, graph-retrieval, reproducibility]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Implement the approved exploratory experiment in a reproducible pipeline that freezes the 30-question Gold ledger, isolates inference inputs, generates connected graph evidence chains, ranks them under five locked conditions, evaluates exact-chain retrieval, and writes manuscript-ready results.

## 1. Requirements & Constraints

- **REQ-001**: Preserve original review workbooks, consensus workbook, registry, and canonical graph without modification.
- **REQ-002**: Finalize exactly 30 questions with 10 questions in each prespecified category.
- **REQ-003**: Write a sanitized inference file containing no answer, node, edge, target, reviewer, adjudication, or Gold fields.
- **REQ-004**: Generate connected evidence chains with one to five canonical edge triples from the fixed task-graph projection.
- **REQ-005**: Use identical candidates for B0, M0, cue-off, direction-off, and R1.
- **REQ-006**: Write `method_lock.json` before evaluation and reject hash/config mismatches.
- **REQ-007**: Report exact-chain Hit@1, Hit@3, Hit@5, MRR, candidate recall, category slices, paired bootstrap intervals, and wording sensitivity.
- **CON-001**: Treat all results as feedback-driven exploratory evidence, not confirmatory evidence.
- **CON-002**: Candidate generation and ranking must not read Gold fields.
- **CON-003**: Do not add private review workbooks, local output archives, API keys, or canonical data artifacts to the public Git repository.
- **PAT-001**: Follow the existing `tools/<experiment>/` package pattern and JSON/Markdown output conventions.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Finalize and lock the reviewed data layer.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `tools/relation_chain_ranking/finalize.py` to validate returned reviews and consensus, apply six decisions, check 30/category counts, and write private and sanitized ledgers. | Yes | 2026-07-18 |
| TASK-002 | Add integrity hashing for registry, reviews, consensus, nodes, edges, and generated ledgers. | Yes | 2026-07-18 |
| TASK-003 | Add a question-ambiguity audit that reports graph alternatives without silently editing adjudicated wording. | Yes | 2026-07-18 |

### Implementation Phase 2

- GOAL-002: Implement locked candidate generation and ranking.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add graph loading, parallel-edge merging, alias construction, anchor detection, and fixed projection in `core.py`. | Yes | 2026-07-18 |
| TASK-005 | Add deterministic connected-chain enumeration with five-edge, 50,000-candidate, 64-anchor, and 2,000,000-work-unit limits. | Yes | 2026-07-18 |
| TASK-006 | Add B0, M0, cue-off, direction-off, and R1 feature computation and stable ranking in `rank.py`. | Yes | 2026-07-18 |
| TASK-007 | Add a lock writer containing normative aliases, stop list, weights, limits, hashes, and Git commit. | Yes | 2026-07-18 |

### Implementation Phase 3

- GOAL-003: Evaluate, verify, and publish the supplementary result.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Add exact-chain metrics, category macros, 10,000-replicate stratified paired bootstrap, and original-versus-revised sensitivity in `evaluate.py`. | Yes | 2026-07-18 |
| TASK-009 | Add focused tests in `tests/test_relation_chain_ranking.py` and run the relevant test suite. | Yes | 2026-07-18 |
| TASK-010 | Execute finalization, lock, inference, and evaluation in separate commands; preserve all JSON/Markdown outputs. | Yes | 2026-07-18 |
| TASK-011 | Update public experiment documentation and the English LaTeX manuscript with only verified results and limitations. | Yes | 2026-07-18 |
| TASK-012 | Compile the paper, inspect warnings, commit public code/docs, and push `main`. | | |

## 3. Alternatives

- **ALT-001**: A supervised graph path ranker was rejected because 30 questions cannot support credible training and model selection.
- **ALT-002**: Direct LLM path selection was rejected as the primary comparison because prompt sensitivity and stochasticity weaken auditability.
- **ALT-003**: Query-specific relation filtering was rejected because it would give the traversal baseline a semantically filtered candidate set.

## 4. Dependencies

- **DEP-001**: Python standard library for graph loading, hashing, serialization, and deterministic enumeration.
- **DEP-002**: NumPy for reproducible `PCG64` paired bootstrap calculations.
- **DEP-003**: Frozen graph files under `artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda/`.
- **DEP-004**: Reviewed registry and extracted final consensus under `outputs/multihop_graph_review_2026-07-18/`.

## 5. Files

- **FILE-001**: `tools/relation_chain_ranking/__init__.py`
- **FILE-002**: `tools/relation_chain_ranking/config.py`
- **FILE-003**: `tools/relation_chain_ranking/core.py`
- **FILE-004**: `tools/relation_chain_ranking/finalize.py`
- **FILE-005**: `tools/relation_chain_ranking/rank.py`
- **FILE-006**: `tools/relation_chain_ranking/evaluate.py`
- **FILE-007**: `tests/test_relation_chain_ranking.py`
- **FILE-008**: `docs/relation_chain_ranking_30_exploratory_2026-07-18.md`
- **FILE-009**: English LaTeX section/table files selected after results are known.

## 6. Testing

- **TEST-001**: Verify finalization applies all six consensus decisions and preserves 24 non-disputed records.
- **TEST-002**: Verify sanitized inference contains none of the forbidden Gold keys.
- **TEST-003**: Verify alias normalization and collision retention are deterministic.
- **TEST-004**: Verify connected-chain enumeration supports linear and branching chains and respects canonical signatures.
- **TEST-005**: Verify parallel edges merge provenance without changing candidate identity.
- **TEST-006**: Verify cue-off does not consult relation aliases and direction-off removes only orientation.
- **TEST-007**: Verify Hit@k, MRR, candidate recall, category macros, and bootstrap reproducibility.
- **TEST-008**: Verify method-lock hashes are checked before evaluation.

## 7. Risks & Assumptions

- **RISK-001**: Questions were constructed from known graph relations, so scores may overestimate performance on arbitrary unseen graph questions.
- **RISK-002**: Some final wording may admit multiple graph-consistent answers; the ambiguity audit must disclose these cases.
- **RISK-003**: Candidate enumeration may hit the deterministic cap for high-degree anchors; cap failures remain in metric denominators.
- **ASSUMPTION-001**: Each finalized question has one adjudicated canonical Gold chain.
- **ASSUMPTION-002**: The fixed relation projection contains the evidence relations required by the reviewed task categories.

## 8. Related Specifications / Further Reading

[Approved design specification](../docs/superpowers/specs/2026-07-18-relation-aware-graph-path-ranking-design.md)

[Review protocol](../docs/multihop_graph_review_protocol_2026-07-18.md)
