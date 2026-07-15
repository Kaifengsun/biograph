# DeepSeek-V4-Pro Full Enrichment Report

Date: 2026-07-09

## Run Summary

- Output directory: `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4/`
- Model: `deepseek-v4-pro`
- Backend: OpenAI-compatible API
- Prompt versions:
  - Summary: `v2_source_grounded`
  - HyDE: `v4_source_grounded_guarded`
  - Table summary: `v3_sha256_source_grounded`
- Canonical artifacts replaced: false
- Neo4j/vector indexes modified: false

The job was run with checkpointing/resume. It completed after two pauses and
resumes. Only the final resumed segment reported `new_llm_calls_this_run = 194`
because previous calls were reused through `_full_enrichment_cache.json`.

## Primary Artifacts

- Run report:
  `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4/_full_enrichment_run_report.json`
- Quality report:
  `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4/_enrichment_quality_report.json`
- Manifest:
  `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4/_enrichment_manifest.json`
- Cache:
  `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4/_full_enrichment_cache.json`

## Coverage

From the quality report:

- Documents: 32 / 32
- Enriched chunks: 2478 / 2478
- Chunks with `enrichment_meta`: 2478 / 2478
- Summary eligible chunks: 427
- Summary generated chunks: 407
- HyDE eligible chunks: 2286
- HyDE generated chunks: 2033
- HyDE questions generated: 3917
- C1 chunks: 1364
- C2 chunks: 922
- Unsupported named-reference questions filtered: 553
- Table rows: 312
- Table rows with summaries: 311
- Table summary coverage: 99.68%

## Additional Audit

A stricter local scan over generated summaries, HyDE questions, and table
summaries found:

- CJK fragments in generated summaries/questions: 0
- Non-question HyDE outputs: 0
- Very short questions: 0
- Questions longer than 340 characters: 0
- Duplicate HyDE question strings: 10
- Median HyDE question length: 134 characters
- Mean HyDE question length: 134.7 characters
- Median summary length: 730 characters

Residual high-consequence supply-chain terms in 3917 HyDE questions:

- `dual-sourcing`: 0
- `contingency`: 2
- `import alert`: 0
- `production halt`: 0
- `recall`: 6
- `contract manufacturer`: 4
- `CMO`: 1
- `supplier`: 20
- `supply chain disruption`: 0
- `regulatory enforcement`: 0
- `enforcement action`: 0

Interpretation: HyDE v4 successfully removed the systematic over-expansion
seen in the previous DeepSeek Flash v3 pilot while preserving broad coverage.

## Current Assessment

This full enrichment run is suitable as the candidate enriched corpus for the
next retrieval experiments. It should still be treated as staging until the
retrieval/evaluation pipeline is rerun and the comparison against the previous
qwen2.5 enrichment is documented.

Recommended next steps:

1. Keep the previous qwen2.5 full enrichment as the baseline enriched corpus.
2. Use this DeepSeek-V4-Pro v4 run as the main candidate enriched corpus.
3. Build or update retrieval indexes from this staging directory only after an
   explicit confirmation, because index replacement affects downstream
   experiments.
4. Run retrieval ablations:
   - baseline chunk text,
   - chunk + summary,
   - chunk + HyDE,
   - chunk + table summaries,
   - full enriched retrieval.
5. Compare retrieval metrics and manual query examples before deciding whether
   to promote this staging run to canonical artifacts.
