# Three-Path Candidate Annotation Pack (2026-07-11)

## Result

`data/eval/three_path_annotation_pack_2026-07-11.json` is a reviewer-ready
candidate pack, not a gold-standard evaluation set. It combines 98 source
records into 84 unique questions without modifying any original candidate file.

| Slice | Unique queries |
| --- | ---: |
| Single clause | 30 |
| Cross-document | 25 |
| Document structure | 7 |
| Table | 21 |
| Supply-chain evidence path | 1 |

Two table records are explicitly marked `excluded` because the frozen corpus
has no viable source table for them. They are not counted as retrieval failures.

## Retrieval Candidate Attachment

`data/eval/three_path_annotation_pack_2026-07-11-with-retrieval.json` attaches
the batch three-path retrieval output from
`artifacts/three_path_retrieval/annotation_candidates_2026-07-11-v1/`.

- All 84 questions received one or more retrieval candidate chunks.
- Mean attached candidate count: 7.7 chunks per question.
- 12 questions received one or more bounded graph-path candidates.
- The pack remains 82 `unreviewed` rows and 2 explicitly excluded rows; no
  attached candidate was promoted to a gold label.

## Review Procedure

For each unexcluded row, the reviewer should:

1. Read the question and inspect its candidate source chunk IDs and document IDs.
2. Confirm one or more chunks that directly support the answer, or record that
   the frozen corpus lacks adequate support.
3. For a graph question, retain only source-backed and answer-relevant path
   nodes; never accept a path merely because the nodes are connected.
4. Change `review_status` to `reviewed`, populate `gold_evidence_chunk_ids`,
   and set `eligible_for_formal_evaluation` to `true` only when the evidence is
   adequate.

The source candidate IDs are aids, not labels. Legacy semantic mappings, table
candidate chunks, and future three-path outputs must all pass this same review.

## LLM-Assisted Review

`data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json` adds a
source-grounded DeepSeek-V4-Pro suggestion for every unexcluded row. The model
could only select from the supplied candidate chunk IDs and its raw JSON output
is preserved in the audit artifact
`artifacts/llm_annotation_review/deepseek-v4-pro-full-2026-07-11/`.

- 82 unexcluded questions received a review suggestion.
- 13 were conservatively marked `insufficient_evidence` by the model.
- The model never created a gold label, changed a reviewer status, or marked a
  row eligible for formal evaluation.

This output should speed up human review: first inspect the 13 insufficient
rows and all cross-document/table/path rows, then confirm the remaining direct
clause suggestions. A model-selected chunk is still only a candidate.

## Reviewer Workbook

`outputs/three_path_annotation_review_2026-07-11.xlsx` is a manually editable
review queue generated from the LLM-assisted pack. It samples 60 unexcluded
questions with fixed slice quotas: 20 single-clause, 20 cross-document, 7
document-structure, 12 table, and 1 supply-chain evidence-path question.

The `Review Queue` sheet exposes candidate IDs, the LLM rationale, bounded
graph paths, and empty fields for reviewer status and gold evidence. It does
not alter the JSON pack and it does not create formal results. The 13 rows for
which the model reported insufficient evidence are intentionally prioritized.

For practical source review, use
`outputs/guided_annotation_review_2026-07-13/three_path_annotation_review_guided_2026-07-13.xlsx`.
It preserves the editable review fields while adding an `Evidence Reader` sheet
with every frozen candidate passage ordered as LLM direct evidence, ranked
retrieval evidence, then additional candidates. Its `Graph Paths` sheet is
read last and provides contextual relationship traces rather than standalone
answer evidence.

After review, `import_three_path_review_workbook.py` validates every confirmed
chunk ID against the frozen corpus and every optional graph node against the
Build5 snapshot. It writes a new reviewed JSON snapshot and cannot overwrite
the source pack. The separate freeze and metrics rules are in
`docs/three_path_formal_evaluation_protocol_2026-07-11.md`.

## Formal Gate

No Recall@k, MRR, nDCG, table-hit, or graph-path success metric may be reported
until a reviewed subset is frozen. The target is a balanced reviewed set of at
least 60 eligible questions, including at least 10 table questions and at least
15 cross-document or graph-path questions.
