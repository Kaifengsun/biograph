---
goal: Build a provenance-preserving experimental graph snapshot for pharmaceutical regulatory evidence retrieval
version: 1.0
date_created: 2026-07-10
last_updated: 2026-07-10
owner: PharmGraphRAG
status: In progress
tags: [architecture, graph, provenance, retrieval, evaluation]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Build a new non-destructive graph snapshot from the frozen DeepSeek v4 enriched corpus. The snapshot must materialize document hierarchy, entity mentions, tables, source provenance, and explicit regulatory references without replacing the existing Neo4j database or canonical vector indexes.

## 1. Requirements & Constraints

- **REQ-001**: Use `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4` as the sole regulatory-corpus input.
- **REQ-002**: Create a separate graph snapshot directory; do not modify source enriched JSON files, `data/vectors`, or the existing Neo4j database.
- **REQ-003**: Materialize `RegulatoryDocument`, `DocChunk`, and `Table` nodes with deterministic IDs.
- **REQ-004**: Materialize `CONTAINS`, `PARENT_OF`, `NEXT`, `HAS_TABLE`, `MENTIONS`, and `REFERENCES` edges with provenance properties.
- **REQ-005**: Derive hierarchy only from source ordering and `level`; label derived edges as `derivation=hierarchy_inference`.
- **REQ-006**: Link entities only through exact normalized aliases from structured entity records; record alias, source text, and linker confidence.
- **REQ-007**: Create only explicit `REFERENCES` edges from source-supported regulatory citations. Do not infer `DEPENDS_ON` or `COVERS` edges.
- **REQ-008**: Aggregate existing source-grounded leaf summaries into section and document summary inputs. LLM generation is separate, checkpointed, and source-grounded.
- **SEC-001**: Read API keys from environment variables only; never write them to artifacts or logs.
- **CON-001**: Existing legacy Neo4j data is stale relative to the 2,478-chunk corpus and is read-only reference data.
- **CON-002**: Formal retrieval labels are not yet frozen; graph artifacts must preserve enough provenance for later review.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Build and validate a deterministic local graph snapshot without external API calls.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `build_regulatory_evidence_graph.py` to load frozen enriched chunks and table files, create document/chunk/table nodes, and emit JSONL nodes and edges. | Yes | 2026-07-10 |
| TASK-002 | Reconstruct parent-child edges by assigning each chunk to the nearest preceding lower-level chunk in the same document; attach level-1 chunks to the document node. | Yes | 2026-07-10 |
| TASK-003 | Emit `NEXT` edges from `next_chunk_id`, preserving parser-provided order and source provenance. | Yes | 2026-07-10 |
| TASK-004 | Load structured entity aliases from existing pharmaceutical supply-chain source data and create typed `MENTIONS` candidate edges only for exact normalized matches. | Yes | 2026-07-10 |
| TASK-005 | Parse explicit ICH, EMA, FDA, and CFR citations from chunk text and emit source-supported `REFERENCES` edges to known regulatory documents or unresolved reference nodes. | Yes | 2026-07-10 |
| TASK-006 | Emit a manifest and audit report with node/edge counts, hierarchy coverage, entity-link coverage, unresolved references, and source hashes. | Yes | 2026-07-10 |

### Implementation Phase 2

- **GOAL-002**: Prepare hierarchy-summary inputs and validate aggregation provenance.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Add `prepare_hierarchy_summary_inputs.py` to group leaf summaries by materialized parent section and document. | Yes | 2026-07-10 |
| TASK-008 | Emit deterministic section and document summary-input JSONL records containing only child summaries, headings, source chunk IDs, and truncation metadata. | Yes | 2026-07-10 |
| TASK-009 | Add `generate_hierarchy_summaries.py` with checkpoint/resume, DeepSeek API environment configuration, strict source-grounded prompts, and no-overwrite output behavior. | Yes | 2026-07-10 |
| TASK-010 | Run local aggregation validation before any paid API calls; separately report expected call count and maximum input lengths. | Yes | 2026-07-10 |

### Implementation Phase 3

- **GOAL-003**: Make the snapshot ready for later retrieval and Neo4j staging import.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Add unit tests for hierarchy reconstruction, table relationships, explicit reference extraction, and entity-link precision safeguards. | Yes | 2026-07-10 |
| TASK-012 | Produce a non-destructive import manifest for a future separate Neo4j database or namespace; do not perform the import in this plan. |  |  |
| TASK-013 | Update the retrieval experiment documentation with the graph-snapshot identifier and relation semantics. |  |  |

## 3. Alternatives

- **ALT-001**: Modify frozen enriched JSON in place to add parent IDs. Rejected because it invalidates the existing frozen corpus and retrieval artifacts.
- **ALT-002**: Use LLMs to infer all cross-document dependency and coverage relations. Rejected because unsupported edges would weaken provenance and causal claims.
- **ALT-003**: Reuse the current Neo4j graph directly. Rejected because its DocChunk identifiers and MENTIONS coverage do not align with the frozen corpus.

## 4. Dependencies

- **DEP-001**: Frozen corpus at `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4`.
- **DEP-002**: Structured pharmaceutical entity source in `pharma_supply_chain/core_data.py` and FDA enrichment records.
- **DEP-003**: `DEEPSEEK_API_KEY` only for Phase 2 summary generation.

## 5. Files

- **FILE-001**: `build_regulatory_evidence_graph.py` - staged node/edge builder.
- **FILE-002**: `prepare_hierarchy_summary_inputs.py` - deterministic aggregation input builder.
- **FILE-003**: `generate_hierarchy_summaries.py` - checkpointed source-grounded hierarchy summary generator.
- **FILE-004**: `tests/test_regulatory_evidence_graph.py` - graph snapshot tests.
- **FILE-005**: `artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4/` - generated graph snapshot.

## 6. Testing

- **TEST-001**: Every chunk has exactly one incoming `CONTAINS` or `PARENT_OF` edge.
- **TEST-002**: Every non-root chunk has at most one inferred parent and no hierarchy cycle exists.
- **TEST-003**: Every `HAS_TABLE` edge points to an existing parent chunk and deterministic table node.
- **TEST-004**: Every `MENTIONS` edge includes an exact alias evidence span and typed source entity.
- **TEST-005**: Every `REFERENCES` edge includes a matched source span and source chunk ID.
- **TEST-006**: Hierarchy summary inputs contain only summaries from directly related child chunks or sections.

## 7. Risks & Assumptions

- **RISK-001**: Some documents have shallow heading extraction, so inferred document hierarchy may be broad rather than semantically granular.
- **RISK-002**: Structured entity lists include hand-curated supply-chain facts; they must be marked as structured-source provenance, not regulatory proof.
- **RISK-003**: Exact alias matching prioritizes precision over recall; lower-precision semantic linking will be evaluated separately.
- **ASSUMPTION-001**: Explicit regulatory citations are sufficient for the first cross-document relation layer.
- **ASSUMPTION-002**: Hierarchical summaries are retrieval aids and never replace leaf chunk evidence.

## 8. Related Specifications / Further Reading

- `docs/retrieval_experiment_matrix_2026-06-10.md`
- `docs/retrieval_ablation_screening_2026-07-10.md`
- `docs/deepseek_v4_pro_full_enrichment_report_2026-07-09.md`
- `CODEX_RULES.md`
