# Adaptive Text-First Retrieval: Held-Out Evaluation Protocol

## Research decision

The retrieval system is positioned as text-first. Bottom-up source-chunk retrieval and top-down document routing are the primary retrieval mechanisms. Graph retrieval is an optional evidence-routing and structured-trace validation mechanism, not a standalone replacement for semantic retrieval.

## Dataset roles

- Development set: the 60-query snapshot `three_path_evaluation_frozen_2026-07-15.json`. It has already been used for ablation and error analysis and must not be described as an untouched test set after further method changes.
- Held-out test candidate set: 30 new human-reviewed queries assembled before adaptive-fusion implementation.
- Held-out composition target: 10 single-clause, 6 table, 4 cross-document, 4 document-structure, and 6 supply-chain graph-path queries.
- The held-out set must be human-reviewed and frozen before implementation begins.
- No retrieval run, parameter search, or result inspection is permitted on held-out queries until the adaptive policy and all baselines are locked.

## Progressive experiment stages

### Stage 1: Reproducible baseline

Status: complete.

- Reproduce Bottom-up, Top-down, Graph path, pairwise RRF, and three-path RRF on the 60-query development set.
- Preserve the current immutable rankings and hashes.
- Completion criterion: formal metrics and post-hoc ablation agree exactly; all tests pass.

### Stage 2: Text-first development

Use only the 60-query development set.

- Improve explicit regulatory-document routing for queries that name an authority, guideline, annex, or section.
- Improve table-query handling using document/table metadata and heading-aware evidence ranking.
- Replace unconditional three-way RRF with an adaptive graph gate. Graph evidence may contribute only when a recognized entity/topic anchor reaches a relevant regulatory document or a directly matched structured event.
- Prevent fusion dilution by retaining strong evidence from a component route when fusion would move it below rank 5.

Development parameters may include document budget, route-retention threshold, graph-gate confidence, and graph contribution weight. Search ranges and the final choice must be recorded before held-out execution.

Completion criteria:

- Development Hit@5 is not lower than the current text-fusion baseline of 0.833.
- No component-route gold evidence at rank 1-5 is pushed below rank 5 without a higher-confidence replacement.
- Graph contribution remains auditable and separate from structured-path validation.
- Unit and integration tests pass.

### Stage 3: Locked held-out execution

- Freeze code revision, parameters, indexes, graph snapshot, and corpus hashes.
- Run every predeclared baseline and the final adaptive method exactly once on the 30-query held-out set.
- Primary metric: Hit@5.
- Secondary metrics: Hit@1, Hit@3, MRR, nDCG@5, and graph-path success for reviewed path queries.
- Report paired query-bootstrap 95% confidence intervals.
- Use exact paired McNemar tests for Hit@K and paired Wilcoxon tests for MRR/nDCG, with Holm correction within each named hypothesis.

### Stage 4: Predeclared held-out ablations

- Bottom-up only.
- Top-down only.
- Bottom-up + Top-down RRF.
- Unconditional three-path RRF.
- Adaptive text-first method without graph contribution.
- Full adaptive text-first method with graph contribution.

These variants use the same locked rankings and parameters. No post-test tuning is allowed.

## Reproducibility notes

The retriever is deterministic for fixed model weights, indexes, graph, corpus, and parameters; repeated random seeds do not represent independent training runs. Statistical uncertainty is therefore estimated by paired query bootstrap rather than artificial multi-seed reruns. Every run must be appended to `outputs/experiment_notes/adaptive_text_first_2026-07-15/notes.txt`.

## Human review rule

For each held-out query, the reviewer must mark `Confirmed`, `Revise`, or `Exclude` and verify text gold chunks against the frozen source passages. For supply-chain cases, structured nodes are reviewed separately and must never be entered as text gold chunk IDs.
