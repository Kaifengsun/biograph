# Regulatory Evidence Graph Snapshot (2026-07-10)

## Scope

This report records a non-destructive graph snapshot built from the frozen DeepSeek-V4-Pro enriched regulatory corpus. It does not modify the existing Neo4j database, canonical vector indexes, or source enriched JSON artifacts.

## Snapshot

- Final snapshot: `artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build4-hierarchy/`
- Frozen regulatory corpus: 32 documents and 2,478 chunks.
- Node count: 3,961.
- Edge count: 9,898.
- Summary generator: `deepseek-v4-pro`, prompt `v1_hierarchy_source_grounded`.

## Materialized relations

| Relation | Count | Meaning |
| --- | ---: | --- |
| `CONTAINS` | 1,722 | Document-to-root chunk membership. |
| `PARENT_OF` | 756 | Parent-child chunk relation derived from parser order and levels. |
| `NEXT` | 2,446 | Parser-provided neighboring chunk sequence. |
| `HAS_TABLE` | 312 | Table artifact explicitly linked to its parent chunk. |
| `MENTIONS` | 230 | Exact normalized alias match from a chunk to a structured entity. |
| `REFERENCES` | 602 | Explicit ICH/EMA/FDA/CFR citation in source text. |
| `CONTAINS_API` | 134 | Structured drug-to-API relation. |
| `SUPPLIED_BY` | 329 | Structured API-to-manufacturer relation. |
| `WAS_RECALLED` | 363 | FDA enrichment drug-to-recall signal relation. |
| `RECALLED_BY` | 355 | FDA enrichment recall-to-reporting-firm relation. |

There are 355 unique dated FDA recall events. They are evidence-bearing historical signals, not labels proving a future shortage.

## Hierarchical summaries

The graph includes 221 section summaries and 32 document summaries. Summary nodes use `HAS_SECTION_SUMMARY` or `HAS_DOCUMENT_SUMMARY` from the summarized node and `SUMMARIZES` edges back to direct child chunks or lower-level summaries.

- 175 hierarchy summaries are retrieval eligible.
- 78 summaries returned `[INSUFFICIENT_SOURCE]`; they remain in the graph for audit but are excluded from retrieval.
- 12 long hierarchy inputs record explicit source truncation metadata.

This preserves the intended bottom-up aggregation pattern without allowing a high-level overview to replace the source chunks that support an answer.

## Cross-document semantics

The first relation layer includes explicit `REFERENCES` only. A textual citation does not establish `DEPENDS_ON`, `COVERS`, causal influence, or regulatory applicability. Those stronger semantics require separate source evidence and, if added, must retain a citation span and provenance field.

The resolver links unique unversioned citations such as `ICH Q2` to the frozen Q2(R2) document, but leaves ambiguous citations such as `ICH Q1` unresolved rather than creating a possibly incorrect edge.

## Limits

- The current snapshot is a local JSONL graph artifact, not yet a replacement Neo4j database.
- Parent-child edges are parser-derived; documents with shallow heading extraction remain structurally broad.
- Exact entity mention coverage is 95 of 2,478 chunks (3.83%). This is intentionally high precision and will be expanded later using auditable entity-linking methods.
- Structured supply-chain relations and FDA recall records need separate source validation before use in a time-split shortage-risk study.

## Next use

The snapshot is ready to support a new staged graph retriever: hybrid bottom-up retrieval, document-tree top-down expansion, and constrained LLM-guided traversal over source-backed candidate paths.
