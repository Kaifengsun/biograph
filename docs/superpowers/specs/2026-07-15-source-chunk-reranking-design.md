# Source-Chunk Reranking Design

## Goal

Improve regulatory evidence retrieval without allowing summaries, HyDE questions, or table summaries to occupy source-chunk ranking positions. The design must preserve BM25's strong lexical recall while using dense similarity, document hierarchy, and graph evidence only where each signal is appropriate.

## Evidence Behind The Design

The already-observed 30-query ablation set (`query_content_sha256=3f05df3c4fa86c69a8d15abb579f5e012a0ecddff3e9b8046d9eb7c21d76b4f6`) showed that BM25 was the strongest overall source-chunk retriever, while the existing adaptive hierarchy was strongest on the eight table queries. Because these results motivated this design, that set is now an observed validation set and cannot be reused for a new confirmatory claim. Flat insertion of generated sidecars reduced ranking quality because multiple vectors belonging to one source chunk competed with source chunks for a limited top-k. The graph recovered structured shortage paths but did not improve ordinary text ranking.

## Considered Approaches

### A. Global weighted score

Normalize BM25 and dense scores and apply one weight vector to every query. This is simple and reproducible, but ignores the observed difference between single-clause and table queries.

### B. Query-routed source-chunk reranking (selected)

Create a candidate union from BM25 source chunks and raw source-chunk dense retrieval. Rerank only source chunks. Preserve BM25 unchanged by default. Enable dense fusion only when the query contains explicit table intent or the source-only candidate pool contains enough independent table evidence. The final implementation does not use generated summaries, HyDE questions, or table-summary sidecars as candidates or score features. Invoke graph retrieval only for structured entity-relation queries and report it separately from text metrics.

This approach is selected because it matches the observed failure modes, is auditable, and retains a small parameter space suitable for the 60-query development set.

### C. LLM or cross-encoder reranking

Send each query-candidate pair to a large model or cross-encoder. This may improve semantic ordering, but introduces model cost, nondeterminism, and an additional model-selection problem. It is deferred until the deterministic reranker is measured.

## Architecture

### Candidate generation

- Build BM25 over frozen source chunks using lowercase ASCII-alphanumeric tokenization over `parents_context + heading + content`, truncated to the same 2,000 characters used by the dense index. Use `k1=1.2` and `b=0.75`.
- Retrieve raw source-chunk dense candidates from the frozen R1 `IndexFlatIP` index built with `tencent/Youtu-Embedding`. R1 embeds the exact same `parents_context + heading + content` payload and 2,000-character truncation used by BM25. Query and corpus vectors are L2-normalized, so inner product is cosine similarity.
- Take the ordered union of the top 30 BM25 and top 30 dense candidates.
- Never add summary, HyDE, or table-summary records as candidates.
- Use the same 2,478 canonical chunk IDs and the same human-confirmed qrels for every text baseline. Map any legacy sidecar hit to its owning chunk and deduplicate before metric calculation.

### Features

For every candidate source chunk, calculate these exact values:

- BM25 reciprocal rank `1 / (60 + rank_bm25)`, or zero when absent from top 30.
- Raw dense reciprocal rank `1 / (60 + rank_dense)`, or zero when absent from top 30.
- Explicit document-name match. Normalize the query and each `doc_id` to lowercase ASCII-alphanumeric tokens. Generate aliases using the existing `adaptive_text_first.document_aliases` rules. The feature is one only when a complete alias occurs as a token-bounded contiguous query phrase.
- Table evidence indicator. The feature is one when the normalized heading contains token-bounded `table`, the normalized first 800 content characters contain token-bounded `table`, or the owning chunk ID occurs in a frozen `*_tables.json` record; otherwise it is zero. This rule uses ASCII matching plus structured table membership and does not depend on localized marker encoding.
- Top-down selected-document membership. Use the stored order of `top_down.selected_documents`; represent membership as `1 / (60 + one_based_selected_document_rank)`, or zero when the candidate document is not selected.

Binary explicit-document and table indicators contribute their configured weight divided by 61. No min-max normalization is used, so zero-range behavior is not applicable.

### Query routing

Use lowercase ASCII-alphanumeric tokenization and deterministic term lists stored in code and in the method lock. Produce one text route and an independent Boolean graph gate:

- `lexical`: explicit standard/document identifiers or exact regulatory terminology; BM25 dominates.
- `table`: table-related terms; table and hierarchy features are enabled.
- `hierarchy`: section/document-structure intent; the selected-document feature is enabled.
- `semantic`: paraphrastic queries without explicit identifiers; dense weight increases.
- `graph_gate`: drug, API, NDC, manufacturer, shortage, or typed relationship intent; text ranking still follows one of the four text routes and graph paths are returned as separate verification evidence.

Text-route precedence is `table`, `hierarchy`, `lexical`, `semantic`. The graph gate does not change text scores.

### Score and safeguards

The first routed implementation applied BM25 and dense fusion to every route and failed on the observed 30-query validation set, especially for cross-document questions. The final selective score is therefore:

`bm25_rr + dense_rr + table_weight * table_indicator / 61` when the table gate is enabled; otherwise return the original BM25 ranking unchanged.

The table gate is true when the deterministic query router returns `table`, or when at least `table_support_threshold` unique canonical table chunks occur in the union of the first `table_support_depth` BM25 and dense results. The final compact grid contains `table_support_depth in {3, 5, 10}`, `table_support_threshold in {1, 2, 3}`, and `table_weight in {0.0, 0.25, 0.5, 1.0}`. Parameters are selected on the combined 90 observed queries. For tie-breaking, a missing top-30 rank is positive infinity. Final ties are broken by lower BM25 rank, then lower dense rank, then lexicographic chunk ID. Safeguards are:

- When the table gate is disabled, return BM25 exactly, including order and output depth.
- Do not use graph reachability as a generic text relevance feature.
- Record every route, feature value, component contribution, and final score.

## Experimental Protocol

1. Use the frozen 60-query development set plus the already-observed 30-query ablation set as a combined 90-query development set. The latter cannot serve as confirmation because its results motivated the selective gate. Record both query hashes in the method lock.
2. Compare source-only, depth-matched `BM25`, `R1 raw dense`, `global source reranker`, and `query-routed source reranker` on development data. Report the existing adaptive system only as an augmented historical reference because its sidecar-first retrieval pool is not source-only and is not depth-matched; it is excluded from confirmatory superiority tests.
3. Select parameters lexicographically by MRR, Hit@5, nDCG@5, then by fewer nonzero features, lower summed parameter magnitude, and finally the lexicographic tuple `(lexical_bm25_weight, semantic_dense_weight, explicit_document_weight, table_weight, hierarchy_weight)`.
4. Lock code hashes, data hashes, candidate depths, routing rules, and weights after the combined 90-query development run and before new confirmatory-set construction.
6. Construct a new 30-query confirmatory set by deterministic stratified sampling with seed `20260716` from an eligible question pool created before this reranker and excluding every question or source question used in the existing 90 queries. Freeze 10 `single_clause`, 8 `table`, 6 `document_structure`, and 6 `cross_document` questions. During selection, query authors/selectors may inspect source documents and slice labels but cannot inspect BM25, dense, routed-reranker, or graph outputs. Build each gold-review passage pool independently of the compared systems: include the source chunk originally attached to the pre-existing question, its immediate previous and next chunks within the same document when present, its parent-section siblings up to a deterministic cap of eight passages, and four corpus distractors selected by SHA-256 ordering of `seed:query_id:chunk_id`. Human gold review uses these anonymized, deterministically shuffled passages without method names, scores, or ranks. Record zero query-ID and zero normalized-question overlap, sampling inputs, exclusions, passage-pool construction, shuffle seed, reviewer decisions, and final query hash before the one-time formal run.
7. Report Hit@1/3/5, MRR, nDCG@5, paired bootstrap 95% confidence intervals, an exact McNemar test for Hit@5, and paired Wilcoxon tests for MRR/nDCG@5. Use seed `20260715`, 10,000 bootstrap iterations, and Holm correction across the three confirmatory metric tests.
8. Report graph path recovery separately as structured evidence coverage; do not mix graph nodes into chunk ranking metrics.
9. Hash the corpus files, index and metadata, embedding configuration, code, routing terms, candidate depths, tie rules, package versions, random seed, development set, observed validation set, and new confirmatory set in the method and evaluation manifests.

## Success Criteria

The primary confirmatory outcome is overall MRR versus context-matched BM25. Confirmatory success requires all four conditions: paired mean MRR delta greater than or equal to 0.03, paired bootstrap 95% CI lower bound greater than zero, Holm-adjusted paired Wilcoxon `p < 0.05`, and no Hit@5 decrease larger than 0.033. Hit@5 and nDCG@5 are secondary outcomes in the same Holm family. A Hit@5 increase of at least 0.067 (two of 30 queries) is considered practically notable but does not replace the primary success conditions.

The four pre-registered slices are `single_clause`, `table`, `document_structure`, and `cross_document`; their membership is frozen with the new confirmatory pack. Slice results are descriptive because of small sample sizes and cannot independently establish confirmatory success. Any new route or slice discovered after evaluation is explicitly exploratory and requires a future untouched set.

## Testing

- Unit-test routing precedence and route labels.
- Unit-test source-chunk deduplication and rejection of sidecar IDs.
- Unit-test normalization, score decomposition, and deterministic tie-breaking.
- Verify no sidecar ID appears in final source-chunk rankings.
- Verify that the development, observed validation, and new confirmatory sets have zero query-ID and normalized-question overlap, and verify all method-lock hashes.
- Run the complete existing test suite before formal evaluation.
