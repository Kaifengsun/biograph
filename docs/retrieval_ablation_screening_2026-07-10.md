# Retrieval Ablation Screening Record (2026-07-10)

## Scope and fairness boundary

The historic local Qwen2.5 enrichment corpus is an end-to-end system baseline only. It differs from the current DeepSeek corpus in both model and enrichment prompt/runtime (v3 versus v4), so it must not be presented as a causal model comparison.

Model selection was instead based on the controlled 13-document pilot: Qwen3.7-Max and DeepSeek-V4-Pro used the same source sample, v4 guarded prompts, temperature, and thinking-disabled API configuration. DeepSeek-V4-Pro was selected because it retained more grounded HyDE coverage while satisfying the same formatting and source-grounding checks. The frozen full corpus is `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4`.

## Index variants

All variants are staging-only outputs under `artifacts/retrieval_ablation/deepseek-v4-pro-v4/`; no canonical vector index or graph database was replaced.

| Variant | Indexed representation | Vector count |
| --- | --- | ---: |
| R1 | Raw chunks | 2,478 |
| R2 | Source-grounded chunk summaries | 2,478 |
| R3 | R2 plus generated HyDE questions | 6,395 |
| R4 | R3 plus source-grounded table summaries | 6,706 |

## Document-level screening result

The 40 legacy annotated queries have stable relevant-document labels, but their chunk identifiers refer to the old segmentation. Therefore this screening uses only document-level metrics and is not a formal chunk-level retrieval result.

| Variant | DocHit@1 | DocHit@5 | DocMRR |
| --- | ---: | ---: | ---: |
| R1 raw | 0.4250 | 0.7750 | 0.5838 |
| R2 summary | 0.4500 | 0.8000 | 0.6049 |
| R3 + HyDE | 0.5750 | 0.7500 | 0.6676 |
| R4 + table summary | 0.5750 | 0.7500 | 0.6676 |

Interpretation for internal decision-making:

- Summaries improve broad document coverage and ranking over raw chunks.
- HyDE has the strongest top-rank improvement: DocHit@1 rises from 0.425 to 0.575 and DocMRR from 0.5838 to 0.6676 versus R1.
- R4 ties R3 because the existing 40-query set lacks table-specific questions; this is a test-set coverage limitation, not evidence that table summaries are ineffective.

## What can and cannot enter the paper now

The controlled model-selection pilot and the above document-level results can be reported as development evidence with their stated scope. They must not be reported as final chunk-level Recall@k, MRR, nDCG, or table-retrieval evidence.

`data/eval/eval_queries_deepseek_v4_semantic_candidate_2026-07-10.json` contains 107 semantic candidate mappings for the 40 legacy annotated queries. They are a review aid, not labels: source/subject-matter validation must freeze the final evidence chunks before formal chunk-level metrics are calculated. The evaluation set also needs dedicated table questions before R4 is formally assessed.

## Provisional chunk-level diagnostic

For engineering diagnosis only, the current semantic candidate mappings were used to run a provisional chunk-level screen. The output is `artifacts/retrieval_ablation/deepseek-v4-pro-v4/provisional_chunk_level_ablation_eval.json` and remains explicitly non-formal.

| Variant | ChunkHit@1 | ChunkHit@5 | ChunkMRR |
| --- | ---: | ---: | ---: |
| R1 raw | 0.1000 | 0.4000 | 0.2504 |
| R2 summary | 0.1250 | 0.5000 | 0.2898 |
| R3 + HyDE | 0.1500 | 0.3500 | 0.2269 |
| R4 + table summary | 0.1500 | 0.3500 | 0.2269 |

This apparent divergence is methodologically useful: HyDE improves document-level first-hit ranking, but its sidecar vectors can occupy the top-k vector slots and displace the exact evidence chunks under a flat deduplicated chunk metric. The final system should therefore evaluate (and likely implement) a two-stage policy: use HyDE for document/section navigation, then perform source-chunk reranking or evidence backfill before measuring answer-support retrieval. R4 cannot be assessed from this 40-query set because it has no table-focused questions.

The first two-stage diagnostic is saved at `artifacts/retrieval_ablation/deepseek-v4-pro-v4/two_stage_provisional_eval.json`. With one document selected by HyDE and source chunks then retrieved from R2, provisional ChunkHit@5 is 0.525 and ChunkMRR is 0.3246, compared with 0.350 and 0.2269 for flat R3. Selecting three documents gives the best provisional ChunkRecall@5 (0.3479), while selecting five dilutes the result. These figures remain diagnostic because the evidence labels are not frozen, but they support testing a small document budget followed by source evidence backfill.

## Table-query candidate review

`data/eval/table_query_candidates_deepseek_v4_2026-07-10.json` contains the 12 dedicated table questions from the existing gap-fill plan. Ten have at least one viable table candidate; two are intentionally marked as having no viable table evidence in the frozen corpus: Q1B photostability and Q6B biotechnology-product attributes. They should be repaired by revisiting extraction or excluded from the table ablation, not counted as retrieval failures.

## Next experimental gate

1. Review and freeze the remapped evidence labels, retaining explicit source support for each query.
2. Add and validate a table-focused query slice.
3. Re-run chunk-level R1--R4 metrics on the frozen set.
4. Only then add the structural graph-retrieval variants (R5--R7), so their effect is not confounded with enrichment changes.
