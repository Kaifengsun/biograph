---
goal: Assemble a reviewer-ready candidate annotation pack for three-path retrieval evaluation
version: 1.0
date_created: 2026-07-11
last_updated: 2026-07-11
owner: PharmGraphRAG
status: In progress
tags: [data, evaluation, annotation, retrieval]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Create one non-formal candidate annotation pack from existing regulatory,
gap-fill, table, and graph-path question sources. The pack supports reviewer
validation; it does not create gold labels or formal metrics automatically.

## 1. Requirements & Constraints

- **REQ-001**: Preserve each source query, candidate evidence ID, source file, and exclusion reason.
- **REQ-002**: Deduplicate by normalized query while retaining all source records and candidate evidence IDs.
- **REQ-003**: Preserve no-viable-table records as explicitly excluded rather than treating them as retrieval failures.
- **REQ-004**: Initialize every retained row with empty gold evidence and `review_status=unreviewed`.
- **CON-001**: Do not mark a row eligible for formal evaluation until reviewer validation is recorded.
- **CON-002**: Do not modify existing candidate files or frozen corpus artifacts.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Produce and validate the unified reviewer candidate pack.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `prepare_three_path_annotation_pack.py` to combine four existing query sources into a source-preserving JSON pack. | Yes | 2026-07-11 |
| TASK-002 | Add `tests/test_three_path_annotation_pack.py` for deduplication, exclusion preservation, and empty-gold-label safeguards. | Yes | 2026-07-11 |
| TASK-003 | Generate `data/eval/three_path_annotation_pack_2026-07-11.json` without overwriting prior evaluation files. | Yes | 2026-07-11 |
| TASK-004 | Document pack counts, review procedure, and formal-evaluation gate. | Yes | 2026-07-11 |
| TASK-005 | Batch-run the three-path retriever on all candidate queries and attach its source-chunk and bounded-path candidates without promoting labels. | Yes | 2026-07-11 |
| TASK-006 | Run a checkpointed, candidate-only DeepSeek evidence review and attach 82 non-formal suggestions with raw-output audit trails. | Yes | 2026-07-11 |
| TASK-007 | Generate and visually verify a 60-row balanced Excel review queue without promoting any candidate to a gold label. | Yes | 2026-07-11 |
| TASK-008 | Add validated workbook import, predeclared freeze gates, and formal three-path metrics that reject unreviewed input. | Yes | 2026-07-11 |

## 3. Alternatives

- **ALT-001**: Treat semantic candidate IDs as final labels. Rejected because they have not received source review.
- **ALT-002**: Use LLM-only labels. Rejected because model output can assist review but cannot substitute for evidence validation.

## 4. Dependencies

- **DEP-001**: Existing legacy semantic candidates, gap-fill candidates, table candidates, and three-path diagnostic template.

## 5. Files

- **FILE-001**: `prepare_three_path_annotation_pack.py`.
- **FILE-002**: `tests/test_three_path_annotation_pack.py`.
- **FILE-003**: `data/eval/three_path_annotation_pack_2026-07-11.json`.
- **FILE-004**: `docs/three_path_annotation_pack_2026-07-11.md`.
- **FILE-005**: `outputs/three_path_annotation_review_2026-07-11.xlsx`.
- **FILE-006**: `docs/three_path_formal_evaluation_protocol_2026-07-11.md`.

## 6. Testing

- **TEST-001**: Duplicate query text merges evidence candidates and preserves every source.
- **TEST-002**: No-viable-table rows remain explicitly excluded.
- **TEST-003**: Generated rows have no gold evidence and are ineligible until reviewed.

## 7. Risks & Assumptions

- **RISK-001**: Candidate evidence may be wrong or incomplete; all rows require reviewer validation.
- **ASSUMPTION-001**: Existing candidate sources use UTF-8 JSON and retain their stated provenance.

## 8. Related Specifications / Further Reading

- `plan/feature-three-path-snapshot-retrieval-1.md`
- `docs/three_path_retrieval_pilot_2026-07-11.md`
