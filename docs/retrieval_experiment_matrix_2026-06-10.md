# PharmGraphRAG Retrieval Experiment Matrix

Date: 2026-06-10  
Status: Draft design for post-enrichment evaluation  
Scope: Retrieval and evidence-grounding experiments only. This document does not modify canonical corpus, FAISS indexes, or Neo4j.

## Current Position

The project already has a candidate evaluation pool and annotation guidelines. The main weakness is not the absence of evaluation code, but the lack of a frozen, manually validated query set that stresses the system features we want to claim: C1/C2 HyDE, table summaries, document hierarchy, and graph traversal.

The current full local enrichment run prepares the missing evidence-side artifacts:

| Artifact | Role in experiment |
|---|---|
| `summary` and `search_text` | Tests whether source-grounded summaries improve dense retrieval. |
| `hyde_questions` and `hyde_strategy` | Tests whether generated C1/C2 questions improve query-to-chunk matching. |
| `table_summary` | Tests whether table-bearing evidence becomes retrievable before locating the original table. |
| `enrichment_meta` | Enables quality audit by prompt version, backend model, C1/C2 split, and skipped outputs. |

## Main Claims To Test

1. Source-grounded enrichment improves retrieval over raw chunk text without increasing hallucinated evidence.
2. C1/C2 HyDE improves recall for short, lexically sparse regulatory chunks.
3. Table summaries improve retrieval of table-dependent evidence.
4. Graph expansion improves document-structure and cross-document queries beyond flat vector retrieval.
5. Full PharmGraphRAG gives the largest gains on scenario and cross-document queries, not necessarily on simple single-clause questions.

## Evaluation Set Design

The final paper set should contain 80 to 100 manually validated queries, selected from existing legacy candidates plus the new gap-fill candidates in `data/eval/query_candidates_v2_gap_fill_2026-06-10.json`.

| Query slice | Target count | Purpose |
|---|---:|---|
| `single_clause` | 25-30 | Direct regulatory retrieval; should be competitive for flat RAG. |
| `document_structure` | 15-20 | Tests hierarchy, neighboring clauses, annexes, and section-level navigation. |
| `cross_document` | 20-25 | Tests references, graph walk, and regulatory synthesis. |
| `supply_chain_scenario` | 20-25 | Tests natural decision-support queries without document-name hints. |

At least 10 final queries should require table evidence. At least 20 should be scenario-style queries that do not name the target document.

## Retrieval Variants

### Feasible Core Matrix

These variants match the current codebase and can be implemented without pretending to have external systems fully reproduced.

| ID | Variant | Corpus/index input | Graph access | Purpose |
|---|---|---|---|---|
| R0 | BM25 keyword baseline | Chunk heading + content | No | Lexical baseline through Neo4j full-text or equivalent. |
| R1 | Dense chunk RAG | Raw chunk heading + content | No | Standard vector retrieval baseline. |
| R2 | Dense + summary | `search_text` with generated summary | No | Isolates summary enrichment. |
| R3 | Dense + summary + HyDE sidecar | Chunk text plus generated HyDE questions | No | Isolates C1/C2 question expansion. |
| R4 | Table-aware flat RAG | R3 plus indexed `table_summary` records | No | Isolates table-summary retrieval. |
| R5 | Stage 1 + structural expansion | R4 plus sibling/parent/section expansion | Partial | Tests local document graph context. |
| R6 | Stage 1 + top-down entity graph | R5 plus entity-neighbor expansion | Yes | Tests KG-assisted retrieval without graph walk. |
| R7 | Full PharmGraphRAG | R6 plus graph walk / references | Yes | Proposed method. |

### Optional External Baselines

External baselines such as LightRAG, HippoRAG, Microsoft GraphRAG, or Document-GraphRAG should be included only if we actually run a fair implementation. If time is short, the paper should frame them as related work and report only reproducible internal baselines. A smaller honest table is better than a large table with fragile claims.

## Metrics

| Metric | Use |
|---|---|
| Recall@5/10/20 | Primary retrieval metric for evidence coverage. |
| MRR | Measures whether the first correct evidence appears early. |
| nDCG@10 | Allows graded relevance if label-1 supporting evidence is retained. |
| Table Hit@K | Measures whether a table-bearing chunk or table-summary record is retrieved. |
| Evidence Groundedness | Manual or LLM-assisted audit of whether final answers cite retrieved evidence. |
| Hallucinated Citation Rate | Counts answers citing documents, sections, or standards not supported by retrieved evidence. |
| Latency and LLM calls | Cost analysis for practical decision-support deployment. |

## Query-Slice Hypotheses

| Slice | Expected strongest contributor | Reason |
|---|---|---|
| `single_clause` | R1/R2 | Direct lexical or semantic match is often sufficient. |
| `document_structure` | R5/R6 | Requires parent, sibling, table, or section context. |
| `cross_document` | R6/R7 | Requires references and entity/document graph links. |
| `supply_chain_scenario` | R7 | Requires translating a scenario into regulatory evidence and related graph context. |
| `table` evidence | R4/R5 | Table summaries should make tabular evidence retrievable by natural language. |

## Post-Enrichment Implementation Path

1. Validate the enrichment quality report and spot-check generated summaries, HyDE questions, and table summaries.
2. Freeze the staging corpus as a new canonical experiment corpus only after explicit approval.
3. Build separate indexes for R1-R4 so each enrichment component can be isolated.
4. Resolve candidate evidence IDs against the frozen corpus.
5. Select 80-100 final queries and mark only manually checked rows as `eligible_for_formal_evaluation: true`.
6. Run the retrieval matrix and export per-query rankings, metrics, and error cases.
7. Write Section 5 tables from generated result artifacts only.

## Do-Not-Claim List

Do not claim that table-summary retrieval is already fully evaluated until R4/R5 indexing and table-hit metrics exist. Do not claim C1/C2 HyDE improves retrieval until R2 vs R3 is measured on the same frozen query set. Do not report external baselines unless they are run under the same corpus and query protocol.

