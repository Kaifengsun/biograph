---
goal: Produce a verified English Overleaf manuscript with one locked post-hoc Qwen3 reranker analysis
version: 1.0
date_created: 2026-07-16
last_updated: 2026-07-16
owner: Kaifeng Sun
status: 'In progress'
tags: [paper, latex, reranker, citations, reproducibility]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Implement the approved design in
`docs/superpowers/specs/2026-07-16-english-latex-reranker-design.md` without
changing the frozen 58-query Gold set or presenting the new reranker as a
confirmatory experiment.

## 1. Requirements & Constraints

- **REQ-001**: Use `Qwen/Qwen3-Reranker-0.6B` at one exact Hugging Face revision.
- **REQ-002**: Rerank the context-matched BM25 top 50 and retain all 50 results.
- **REQ-003**: Report Hit@1, Hit@3, Hit@5, Hit@50, MRR@50, and binary nDCG@5.
- **REQ-004**: Build an English LaTeX manuscript with 25--35 verified references.
- **REQ-005**: Attribute the sole-authored manuscript to Kaifeng Sun, China Jiliang University.
- **CON-001**: Do not tune any reranker setting on the observed 58-query set.
- **CON-002**: Label every reranker result as supplementary and post hoc.
- **CON-003**: Do not add figures during this phase.
- **SEC-001**: Do not publish API keys, credentials, source-bearing review files, or copyrighted full text.
- **CIT-001**: Verify every bibliography entry and every distinct citation-backed claim against authoritative sources.
- **REP-001**: Lock model, tokenizer, input serialization, hashes, dependencies, metrics, and execution command before inference.
- **REP-002**: Retain every valid result regardless of direction.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Implement and freeze the supplementary reranker experiment before inspecting scores.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create `tools/modern_reranker_58/` with corpus/candidate preparation, lock validation, inference, evaluation, and validation modules. | | |
| TASK-002 | Add focused tests under `tests/test_modern_reranker_58.py` using a deterministic fake scorer. | | |
| TASK-003 | Resolve and download the exact Hugging Face model revision; record model-file hashes and runtime versions. | | |
| TASK-004 | Generate and commit the lock manifest and frozen BM25 top-50 candidate artifact before model inference. | | |

### Implementation Phase 2

- GOAL-002: Execute and validate the one-shot supplementary reranker analysis.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Run Qwen3 reranker inference once with the locked manifest and checkpointed output. | | |
| TASK-006 | Compute per-query, aggregate, bootstrap, paired, and slice results without changing locked settings. | | |
| TASK-007 | Run `validate_results.py` and retain the complete top-50 rankings and runtime log. | | |

### Implementation Phase 3

- GOAL-003: Construct a verified literature and claim-support ledger.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Audit the nine existing references against official or publisher metadata. | | |
| TASK-009 | Discover and verify 16--26 additional works across the seven approved literature categories. | | |
| TASK-010 | Create `paper/references.bib` and `paper/citation_audit.csv`; reject entries without authoritative metadata and claim support. | | |

### Implementation Phase 4

- GOAL-004: Write the English Overleaf manuscript and supplementary material.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Create the neutral `article` LaTeX project under `paper/` with author metadata, abstract, keywords, declarations, and section includes. | | |
| TASK-012 | Rewrite all scientific sections directly in English using only traceable claims and verified citations. | | |
| TASK-013 | Generate result tables from machine-readable artifacts and write `supplementary.tex`. | | |
| TASK-014 | Create `paper/README.md`, the semantic checklist, and project-group review notes. | | |

### Implementation Phase 5

- GOAL-005: Validate, compile, and package the project-group review draft.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | Implement and run citation, number reconciliation, manuscript, and public-package validators. | | |
| TASK-016 | Compile with the documented `pdflatex/bibtex` sequence and eliminate undefined citations and references. | | |
| TASK-017 | Run the focused and project test suites, inspect the final diff, and commit only public reproducible artifacts. | | |

## 3. Alternatives

- **ALT-001**: Add SPLADE and ColBERT. Rejected because it would turn an application-boundary paper into a broad leaderboard and require new tuning decisions.
- **ALT-002**: Omit a modern reranker. Rejected because it leaves a predictable reviewer concern unanswered.
- **ALT-003**: Treat the 58-query run as confirmatory. Rejected because the set and prior outcomes have already been observed.

## 4. Dependencies

- **DEP-001**: `D:\Anaconda3\python.exe` with PyTorch and Transformers.
- **DEP-002**: Official ModelScope repository `Qwen/Qwen3-Reranker-0.6B`, locked by file hashes.
- **DEP-003**: Frozen pack `data/eval/dual_annotation_58_formal_run_ready_2026-07-16.json`.
- **DEP-004**: Frozen corpus `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4`.
- **DEP-005**: Existing BM25 implementation in `source_chunk_reranker.py`.
- **DEP-006**: A local LaTeX distribution or the bundled document runtime.

## 5. Files

- **FILE-001**: `tools/modern_reranker_58/*.py` - locked reranker workflow and validators.
- **FILE-002**: `tests/test_modern_reranker_58.py` - deterministic unit and integrity tests.
- **FILE-003**: `data/eval/modern_reranker_58_lock_2026-07-16.json` - public lock metadata without private text.
- **FILE-004**: `paper/main.tex`, `paper/sections/*.tex`, `paper/tables/*.tex`, `paper/supplementary.tex` - manuscript source.
- **FILE-005**: `paper/references.bib`, `paper/citation_audit.csv` - verified bibliography and audit.
- **FILE-006**: `paper/validation/*` - validation reports and semantic checklist.
- **FILE-007**: `outputs/modern_reranker_58_2026-07-16/*` - local score and result artifacts, ignored unless a sanitized summary is explicitly approved.

## 6. Testing

- **TEST-001**: Candidate preparation returns exactly 58 queries with unique top-50 source chunk IDs when BM25 supplies 50 candidates.
- **TEST-002**: Deterministic tie-breaking uses BM25 rank and then chunk ID.
- **TEST-003**: Metric implementation matches hand-calculated Hit@K, MRR@50, and nDCG@5 examples.
- **TEST-004**: Lock validation rejects any changed model, payload, corpus, qrels, candidate, or analysis hash.
- **TEST-005**: Result validation rejects missing queries, missing metrics, duplicate candidates, and unreported valid outputs.
- **TEST-006**: Citation validation rejects missing metadata sources, unsupported claims, duplicates, and preprint/publication mislabelling.
- **TEST-007**: Manuscript validation rejects unqualified confirmatory or superiority language for the Qwen3 result.
- **TEST-008**: Public-package scan rejects credential patterns, private workbook names, local paths, and source-passage fingerprints.
- **TEST-009**: LaTeX compilation returns zero errors and zero undefined citation/reference warnings.

## 7. Risks & Assumptions

- **RISK-001**: The 0.6B model may be slow or memory-intensive locally; inference must checkpoint without changing the locked computation.
- **RISK-002**: BM25 top-50 places an upper bound on reranker recall; Hit@50 must be reported.
- **RISK-003**: New references may be discoverable only as preprints; publication status must remain explicit.
- **RISK-004**: Administrative declarations may require confirmation before journal submission; they must not be guessed.
- **ASSUMPTION-001**: The existing 2,478-source-chunk corpus and 58-query pack remain unchanged.
- **ASSUMPTION-002**: The project-group review copy may use a neutral article layout before journal selection.

## 8. Related Specifications / Further Reading

- `docs/superpowers/specs/2026-07-16-english-latex-reranker-design.md`
- `sections/draft_chinese_rewritten.md`
- `data/eval/dual_annotation_58_formal_run_ready_2026-07-16.json`
- https://www.modelscope.cn/models/Qwen/Qwen3-Reranker-0.6B
