---
goal: Build and evaluate a BM25 baseline and frozen corpus-enrichment ablation on an independent 30-query held-out set
version: 1.0
date_created: 2026-07-15
last_updated: 2026-07-15
owner: Codex
status: 'In progress'
tags: [experiment, retrieval, bm25, ablation, paper]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

This plan creates a human-reviewed independent evaluation set, implements fixed BM25 and unified ablation evaluation, executes a locked one-shot experiment, and updates only the Chinese manuscript.

## 1. Requirements & Constraints

- **REQ-001**: Create exactly 30 queries with slice counts 10 single-clause, 8 table, 6 document-structure, and 6 cross-document.
- **REQ-002**: Exclude all source chunks used as gold evidence in the existing 60-query development set and 30-query held-out set.
- **REQ-003**: Include complete source passages and source file identifiers in the review workbook.
- **REQ-004**: Implement BM25 with fixed `k1=1.2`, `b=0.75`, and deterministic lower-case alphanumeric tokenization.
- **REQ-005**: Evaluate BM25, R1, R2, R3, R4, BM25+R4 RRF, and Adaptive-text-first using one metric implementation.
- **REQ-006**: Freeze and hash all inputs before retrieval execution.
- **REQ-007**: Update `sections/draft_chinese_rewritten.md` only after formal results exist.
- **CON-001**: Do not use existing HyDE questions as evaluation questions.
- **CON-002**: Do not expose retrieval candidates before human gold review.
- **CON-003**: Do not modify or replace canonical corpus, graph, or existing FAISS indexes.
- **CON-004**: Do not write an English manuscript in this phase.
- **SEC-001**: Do not store or print API keys.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build and review the independent evaluation candidate pack.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Implement source-unit inventory and prior-gold exclusion in `prepare_bm25_enrichment_heldout_review.py`. | | |
| TASK-002 | Generate a 30-row candidate JSON pack without running retrieval. | | |
| TASK-003 | Create `outputs/bm25_enrichment_heldout_review_2026-07-15.xlsx` with `Review Queue` and `Evidence Reader`. | | |
| TASK-004 | Validate workbook quotas, chunk existence, source text, and prior-gold non-overlap. | | |

### Implementation Phase 2

- GOAL-002: Import human decisions and lock the formal experiment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Implement workbook import and revision handling in `import_bm25_enrichment_review.py`. | | |
| TASK-006 | Freeze exactly 30 confirmed rows in `data/eval/bm25_enrichment_heldout_frozen_2026-07-15.json`. | | |
| TASK-007 | Create a method-lock manifest containing SHA-256 hashes for questions, corpus, indexes, BM25 code, evaluator, and adaptive method. | | |

### Implementation Phase 3

- GOAL-003: Implement and execute the locked retrieval comparison.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Implement deterministic BM25 source-chunk ranking in `bm25_retrieval.py`. | | |
| TASK-009 | Implement unified R1-R4 deduplication, RRF, adaptive retrieval, and metric evaluation in `evaluate_bm25_enrichment_ablation.py`. | | |
| TASK-010 | Add tests for tokenization, BM25 ordering, sidecar-to-source mapping, RRF, overlap rejection, and freeze gates. | | |
| TASK-011 | Run all tests and execute formal retrieval once. | | |

### Implementation Phase 4

- GOAL-004: Analyze results and revise the Chinese manuscript.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Produce aggregate, by-slice, bootstrap, paired-test, and Holm-corrected outputs. | | |
| TASK-013 | Generate Markdown and LaTeX paper tables with source JSON provenance. | | |
| TASK-014 | Update the Chinese abstract, method, experiments, results, discussion, and limitations using only frozen results. | | |
| TASK-015 | Verify every manuscript number against the formal JSON and scan for unsupported claims. | | |

## 3. Alternatives

- **ALT-001**: Reuse the first 30-query held-out set. Rejected because the new experiment was designed after inspecting that set.
- **ALT-002**: Use existing HyDE questions as test queries. Rejected because it directly favors R3 and R4.
- **ALT-003**: Evaluate only document-level retrieval. Rejected because the paper claims exact source-evidence retrieval.

## 4. Dependencies

- **DEP-001**: Frozen corpus at `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4`.
- **DEP-002**: Existing R1-R4 indexes at `artifacts/retrieval_ablation/deepseek-v4-pro-v4`.
- **DEP-003**: Existing adaptive retrieval implementation and method lock.
- **DEP-004**: Python packages `numpy`, `scipy`, `statsmodels`, `faiss`, and an XLSX writer/reader available in the workspace runtime.
- **DEP-005**: Human review of the generated workbook.

## 5. Files

- **FILE-001**: `docs/superpowers/specs/2026-07-15-bm25-enrichment-ablation-design.md`.
- **FILE-002**: `prepare_bm25_enrichment_heldout_review.py`.
- **FILE-003**: `import_bm25_enrichment_review.py`.
- **FILE-004**: `bm25_retrieval.py`.
- **FILE-005**: `evaluate_bm25_enrichment_ablation.py`.
- **FILE-006**: `tests/test_bm25_enrichment_ablation.py`.
- **FILE-007**: `outputs/bm25_enrichment_heldout_review_2026-07-15.xlsx`.
- **FILE-008**: `data/eval/bm25_enrichment_heldout_frozen_2026-07-15.json`.
- **FILE-009**: `outputs/bm25_enrichment_ablation_2026-07-15/`.
- **FILE-010**: `sections/draft_chinese_rewritten.md`.

## 6. Testing

- **TEST-001**: Assert BM25 gives a higher score to a document containing the exact rare query token.
- **TEST-002**: Assert repeated sidecar hits map to one source chunk at its best rank.
- **TEST-003**: Assert prior gold chunk overlap causes candidate-pack validation failure.
- **TEST-004**: Assert slice counts must equal 10/8/6/6 before freezing.
- **TEST-005**: Assert generated representations never appear as gold evidence IDs.
- **TEST-006**: Assert statistical output uses 10,000 bootstrap iterations and seed `20260715`.
- **TEST-007**: Assert the evaluator refuses an unlocked or unreviewed pack.

## 7. Risks & Assumptions

- **RISK-001**: Thirty queries may provide low power for paired significance tests; report confidence intervals and effect sizes.
- **RISK-002**: Table extraction quality may cap R4 performance independently of retrieval quality.
- **RISK-003**: Human question wording may favor lexical overlap; include paraphrased questions and report dense baselines.
- **ASSUMPTION-001**: Existing R1-R4 index hashes remain unchanged through evaluation.
- **ASSUMPTION-002**: The user will review all candidate questions before formal execution.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-15-bm25-enrichment-ablation-design.md`
- `docs/three_path_formal_evaluation_protocol_2026-07-11.md`
- `outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json`
