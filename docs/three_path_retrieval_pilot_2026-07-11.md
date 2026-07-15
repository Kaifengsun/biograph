# Three-Path Snapshot Retrieval Pilot (2026-07-11)

## Scope

This is an engineering pilot, not a formal retrieval evaluation. It uses the
build5 regulatory/FDA graph snapshot, the frozen DeepSeek-V4-Pro corpus, the
existing R2 source-evidence index, and the existing R3 HyDE-navigation index.
It does not use the legacy Neo4j database, legacy chunks, or legacy vector
indexes.

The immutable final pilot output is
`artifacts/three_path_retrieval/pilot_2026-07-11-v9/`. It contains six fixed
diagnostic queries and declares `formal_metrics: false` because no human
reviewer has frozen gold evidence chunks or accepted graph paths yet.

## Implemented Paths

| Path | Role | Final evidence policy |
| --- | --- | --- |
| Bottom-up | Search R2 source-evidence vectors directly. | Returns deduplicated frozen source chunks only. |
| Top-down | Use R3 HyDE vectors to vote for a small document set, then descend with R2 and actual hierarchy edges. | Returns source chunks only; summaries and HyDE questions are routing aids. |
| Graph path | Anchor only typed drugs, APIs, firms, FDA events, regulatory documents/topics/references; walk existing snapshot edges with depth, state, neighbor, and per-anchor path budgets. | Uses graph-reachable documents to constrain R2 source-chunk backfill. |

The graph path cannot traverse a fabricated edge, repeat a node, or silently
connect recall events to shortage events. It records all traversed edges and
their source provenance. A graph route that has no eligible anchor explicitly
abstains instead of returning a speculative path.

## Pilot Observations

- `TP002` (audit trails for GMP computerized systems) anchors the explicit
  `gmp-computerized-systems` topic and graph-backfills source evidence from EMA
  Annex 11; the strongest returned chunk is the Audit Trails clause.
- `TP003` (ICH Q12 and Q10) now reaches both regulatory documents after the
  per-anchor path budget was added. R2 backfill returns an ICH Q12 objective
  chunk rather than a document preamble.
- `TP004` routes the stability-supersession question to ICH Q1A source evidence.
- `TP001` and `TP006` have no typed graph anchor and correctly abstain from the
  graph route, while the bottom-up and top-down paths still return regulatory
  evidence. This is intended behavior, not a failed graph walk.
- `TP005` anchors Carboplatin but reaches only the currently available
  WHO/ICH textual mentions. Whether that path supports a shortage-management
  claim requires human review; the pilot does not assert that it does.

## Engineering Changes Made During Pilot

- Replaced the stale Neo4j-based retrieval controller with
  `three_path_retrieval.py`, which reads build5 JSONL directly.
- Reused the existing R2/R3 FAISS artifacts; no retrieval index was replaced.
- Cached the embedding client, batched query encoding, and reused each query
  vector across R2/R3 to avoid redundant GPU inference.
- Forced the locally cached Youtu embedding model into offline mode. A prior
  mirror metadata check caused connection-reset retries but did not affect any
  graph, corpus, or index artifact.
- Added structural and graph-integrity tests, including generic-anchor
  rejection, complete ICH alias matching, bounded acyclic paths, and source
  evidence backfill.

## Formal Evaluation Gate

Do not report pilot rankings as Recall@k, MRR, nDCG, or evidence-groundedness
results. The next step is reviewer annotation using
`data/eval/three_path_label_template_2026-07-11.json`: each row needs accepted
source chunk IDs, applicable accepted graph paths, and a reviewed status. Only
after this label set is frozen can the three paths be compared statistically.

## Verification

`python -m unittest discover -s tests -p 'test_*.py' -v` completed on
2026-07-11 with 50 passing tests. This includes 13 three-path tests and the
existing corpus, enrichment, graph, evaluation, and simulator test suites.
