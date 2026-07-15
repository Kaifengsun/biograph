# Three-Path Formal Evaluation Protocol

## Purpose

This protocol measures evidence retrieval over the frozen Build5 regulatory
graph and source corpus. It does not measure clinical outcomes, shortage
duration, or causal prediction.

## Evaluation Gate

Only a JSON snapshot with status
`frozen_human_reviewed_evaluation_set` and `formal_metrics_ready: true` may be
evaluated. The snapshot is derived from human workbook decisions and contains
only rows that have direct, frozen-source gold chunk IDs.

The predeclared minimum gate is 60 eligible rows, including 10 table rows and
15 cross-document or supply-chain path rows. Review exclusions and revisions
remain in the review ledger, so the final subset cannot hide them.

## Compared Variants

| Variant | Fixed evidence ranking |
| --- | --- |
| Bottom-up | R2 source-chunk retrieval |
| Top-down | R3 document routing followed by R2 source evidence |
| Graph path | Typed, bounded graph traversal with source-backed evidence |
| Three-path RRF | Reciprocal-rank fusion with `k=60` across the three rankings |

No model, prompt, corpus, retrieval depth, document budget, or fusion constant
may be tuned after the frozen snapshot is evaluated.

## Metrics

Report `Hit@1`, `Hit@3`, `Hit@5`, `MRR`, and `nDCG@5` for exact source-chunk
evidence. Report the table slice separately. For questions with an accepted
graph path, report whether an answer-relevant accepted node sequence appears
within the first five graph paths; if too few paths are reviewed, use this as a
qualitative case analysis rather than a headline aggregate metric.

## Execution

After completing the editable review workbook, create a new reviewed snapshot:

```powershell
python import_three_path_review_workbook.py `
  --pack data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json `
  --workbook outputs/three_path_annotation_review_2026-07-11.xlsx `
  --output data/eval/three_path_annotation_pack_2026-07-11-reviewed.json
```

Freeze it only after the gate passes:

```powershell
python freeze_three_path_evaluation_set.py `
  --pack data/eval/three_path_annotation_pack_2026-07-11-reviewed.json `
  --output data/eval/three_path_evaluation_set_2026-07-11-frozen.json
```

Then evaluate the immutable existing retrieval output:

```powershell
python evaluate_three_path_retrieval.py `
  --pack data/eval/three_path_evaluation_set_2026-07-11-frozen.json `
  --retrieval artifacts/three_path_retrieval/annotation_candidates_2026-07-11-v1/per_query.json `
  --output artifacts/three_path_evaluation/formal_2026-07-11.json
```

The evaluator also writes a Markdown table beside the JSON report. It refuses
to run against candidate-only or merely reviewed, non-frozen input.
