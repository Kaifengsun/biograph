---
goal: Implement reproducible three-path retrieval over the build5 evidence graph snapshot
version: 1.0
date_created: 2026-07-11
last_updated: 2026-07-11
owner: PharmGraphRAG
status: In progress
tags: [feature, retrieval, graph, evaluation, provenance]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Implement a local, non-destructive retrieval layer over
`deepseek-v4-pro-v4-build5-regulatory-fda`. It must support bottom-up evidence
retrieval, top-down document-tree routing, and deterministic constrained graph
path discovery without relying on the stale Neo4j database.

## 1. Requirements & Constraints

- **REQ-001**: Read graph data only from `artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda`.
- **REQ-002**: Reuse R2 source-summary and R3 HyDE FAISS artifacts from `artifacts/retrieval_ablation/deepseek-v4-pro-v4`; do not modify them.
- **REQ-003**: Implement three independently inspectable modes: `bottom_up`, `top_down`, and `graph_path`.
- **REQ-004**: Return leaf source chunks as final evidence; summaries, HyDE records, topics, and graph nodes are retrieval aids only.
- **REQ-005**: Each graph path must use existing snapshot edges, be acyclic, have a bounded depth, and expose every node, edge, and provenance field.
- **REQ-006**: Preserve per-query rankings and diagnostics under a new output directory; never overwrite prior evaluations.
- **REQ-007**: Report engineering diagnostics separately from formal paper metrics until human-validated labels are frozen.
- **CON-001**: Do not read legacy `data/chunks`, `data/vectors`, or the old Neo4j database.
- **CON-002**: Do not call paid LLM APIs in the initial deterministic implementation.
- **CON-003**: Use FDA shortage events as dated evidence nodes, not causal labels or duration forecasts.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Build deterministic snapshot loaders and three retrieval paths.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `three_path_retrieval.py` with JSONL graph loading, source-chunk lookup, adjacency indexes, and R2/R3 FAISS index loading. | Yes | 2026-07-11 |
| TASK-002 | Implement `bottom_up_search(query)` using R2 source-evidence ranking plus R3 document navigation and explicit leaf-chunk deduplication. | Yes | 2026-07-11 |
| TASK-003 | Implement `top_down_search(query)` using HyDE document votes, document-summary/section-summary routing, and `PARENT_OF`/`CONTAINS` descent to source chunks. | Yes | 2026-07-11 |
| TASK-004 | Implement `graph_path_search(query)` using exact entity anchors, admissible relation allowlists, bounded breadth-first path discovery, and source-backed chunk backfill. | Yes | 2026-07-11 |

### Implementation Phase 2

- GOAL-002: Add reproducible pilot execution and integrity tests.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Add `run_three_path_pilot.py` to execute fixed query records, serialize per-path evidence/rankings/paths, and write a manifest with input hashes. | Yes | 2026-07-11 |
| TASK-006 | Add `tests/test_three_path_retrieval.py` covering leaf-evidence output, top-down structural expansion, path edge validity, depth/cycle limits, and graph isolation from stale Neo4j. | Yes | 2026-07-11 |
| TASK-007 | Run an initial pilot on a fixed diagnostic query bundle; label all output as engineering-only. | Yes | 2026-07-11 |

### Implementation Phase 3

- GOAL-003: Prepare the formal experiment gate without generating unsupported metrics.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Add `data/eval/three_path_label_template_2026-07-11.json` containing query slice, evidence chunk IDs, accepted path IDs, and reviewer status fields. | Yes | 2026-07-11 |
| TASK-009 | Create `docs/three_path_retrieval_pilot_2026-07-11.md` with query-level observations, failure taxonomy, and an explicit no-formal-metrics statement. | Yes | 2026-07-11 |
| TASK-010 | Run the full unit-test suite and update this plan with verified results. | Yes | 2026-07-11 |

## 3. Alternatives

- **ALT-001**: Reuse `pharma_graphrag/retriever.py`. Rejected because it reads stale chunks, old FAISS metadata, and the unreconciled Neo4j graph.
- **ALT-002**: Run an LLM-guided graph walker immediately. Deferred because a deterministic graph-path baseline is required before measuring whether constrained LLM edge selection adds value.
- **ALT-003**: Treat current semantic candidate labels as formal metrics. Rejected because they are not human-validated against the frozen segmentation.

## 4. Dependencies

- **DEP-001**: Build5 graph JSONL snapshot.
- **DEP-002**: R2/R3 FAISS retrieval artifacts and their metadata.
- **DEP-003**: Local embedding runtime compatible with the existing R2/R3 index vectors.

## 5. Files

- **FILE-001**: `three_path_retrieval.py` - deterministic three-path snapshot retriever.
- **FILE-002**: `run_three_path_pilot.py` - immutable pilot runner.
- **FILE-003**: `tests/test_three_path_retrieval.py` - retriever tests.
- **FILE-004**: `data/eval/three_path_label_template_2026-07-11.json` - formal-label schema and starter query bundle.
- **FILE-005**: `artifacts/three_path_retrieval/<run_id>/` - pilot outputs.
- **FILE-006**: `docs/three_path_retrieval_pilot_2026-07-11.md` - engineering report.

## 6. Testing

- **TEST-001**: Bottom-up output contains only frozen leaf `DocChunk` evidence IDs.
- **TEST-002**: Top-down output reaches source chunks through actual `CONTAINS` or `PARENT_OF` edges.
- **TEST-003**: Every graph path edge exists in the build5 edge JSONL and path depth is within the configured bound.
- **TEST-004**: Graph paths do not repeat nodes and do not traverse recall-to-shortage causal edges.
- **TEST-005**: Pilot manifests include all input hashes and state `formal_metrics=false`.

## 7. Risks & Assumptions

- **RISK-001**: R2/R3 FAISS artifacts may require a local embedding model that is unavailable; a clear runtime diagnostic must be emitted instead of silently substituting a different model.
- **RISK-002**: Exact entity anchors have low recall; graph-path mode must abstain rather than manufacture a path.
- **RISK-003**: Existing evaluation candidates require review before statistical claims.
- **ASSUMPTION-001**: The build5 graph is the sole graph source for this experiment.
- **ASSUMPTION-002**: The initial pilot validates system behavior, not the paper's retrieval-performance hypothesis.

## 8. Related Specifications / Further Reading

- `plan/data-regulatory-relations-fda-snapshot-1.md`
- `docs/regulatory_relations_fda_snapshot_report_2026-07-10.md`
- `docs/retrieval_ablation_screening_2026-07-10.md`
- `docs/retrieval_experiment_matrix_2026-06-10.md`
