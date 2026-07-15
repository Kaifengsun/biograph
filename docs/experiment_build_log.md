# Experiment Build Log

## 2026-06-02: Pre-Freeze Corpus Diagnostics

Status: diagnostic only. No canonical data files, FAISS indexes, or Neo4j nodes were replaced or deleted.

### Current Artifact Counts

| Artifact | Current count | Status |
|---|---:|---|
| Enriched JSON files | 33 | Present but stale for several documents |
| Enriched JSON chunks | 2,410 | Does not match FAISS or Neo4j |
| Empty enriched chunks | 0 | Healthy |
| FAISS document vectors | 3,500 | Stale or unreconciled |
| FAISS entity vectors | 7,480 | Present |
| Neo4j `DocChunk` nodes | 4,016 | Stale or unreconciled |
| Neo4j `Entity` nodes | 7,480 | Present |

The current artifacts cannot be used as the frozen corpus because enriched JSON, FAISS, and Neo4j do not describe the same chunk set.

### TOC Cleaning Validation

The current local implementation of `pharma_doc_pipeline/step_02_chunk.py` already contains TOC-line handling for spaced-dot page-number patterns such as `. . 34`. The code did not need an additional patch.

Command:

```powershell
$env:PYTHONIOENCODING='utf-8'
D:\Anaconda3\python.exe .\_test_step02_q7.py
```

Observed result for `ich_q7`:

| Check | Result |
|---|---:|
| Original characters | 124,886 |
| TOC lines removed | 112 |
| Parsed headings | 160 |
| Largest level-1 section | 2,002 characters |
| Sections above 10,000 characters | 0 |

Direct in-memory chunking results:

| Document | Existing enriched chunks | Existing maximum characters | Post-clean chunks | Post-clean maximum characters |
|---|---:|---:|---:|---:|
| `ich_q7` | 190 | 103,172 | 156 | 1,978 |
| `ich_q6b` | 75 | 47,579 | 73 | 1,915 |
| `arxiv_supply_chain` | 0 | 0 | 60 | 2,200 |

All 33 Markdown documents were also chunked in memory. The largest resulting chunk was 2,271 characters (`who_stability_q1f`). This supports a scoped artifact rebuild rather than another chunker rewrite.

### Neo4j Read-Only Snapshot

The bundled `diagnose_graph.py` script currently has two reporting issues: Windows console encoding can fail on Unicode output, and line 65 formats a nullable value as a number. A read-only query supplied the usable snapshot:

| Node label | Count |
|---|---:|
| `Entity` | 7,480 |
| `DocChunk` | 4,016 |
| `TableChunk` | 329 |
| `Document` | 35 |
| `Regulation` | 15 |

Important relationship counts:

| Relationship | Count |
|---|---:|
| `FROM_DOCUMENT` | 4,016 |
| `NEXT_CHUNK` | 3,971 |
| `PARENT_CHUNK_OF` | 194 |
| `MENTIONS` | 470 |
| `REFERENCES` | 29 |

Known duplicate ID families in Neo4j:

| Existing IDs | Proposed canonical ID |
|---|---|
| `ema_gmp_annex11`, `ema_gmp_annex_11` | `ema_gmp_annex_11` |
| `ich_q1_draft2025`, `ich_q1_draft_2025` | `ich_q1_draft_2025` |

### Next Approval Gate

The next step is a staged rebuild of canonical enriched JSON and downstream indexes. It replaces large data artifacts and may invoke the configured enrichment LLM for chunks that do not hit cache. It must be announced and confirmed before execution under `CODEX_RULES.md`.

## 2026-06-02: Non-Destructive Raw Chunk Staging

Added `prepare_corpus_staging.py` and ran it once. The script writes only to `data/staging/chunks_2026-06/`, applies explicit ID normalization, and refuses to overwrite staging JSON if run again against the same directory.

| Check | Result |
|---|---:|
| Staged Markdown documents | 33 |
| Staged raw chunks | 2,538 |
| Maximum staged chunk length | 2,271 characters |
| Canonical ID normalization | `ema_gmp_annex11` -> `ema_gmp_annex_11`; `ich_q1_draft2025` -> `ich_q1_draft_2025` |
| Existing canonical artifacts replaced | No |
| LLM calls | 0 |
| Neo4j writes | 0 |

The overwrite guard was verified by running the script a second time: it stopped before writing because the staging directory already contained JSON files.

### Enrichment Cost Gate

Current `data/pipeline_cache/enrichment_cache.json` contains 4,295 cached entries. Against the staged raw chunk set, the current enrichment implementation would require:

| Call category | Expected calls | Cache hits |
|---|---:|---:|
| Summary generation | 463 | 135 |
| HyDE generation | 2,344 | 613 |
| Base new API calls | 2,059 | n/a |

The base estimate excludes table-summary calls and therefore is a lower bound. `MOONSHOT_API_KEY` is not currently present in the environment. Full enrichment remains paused until the user approves paid API use or selects a local/pilot alternative.

## 2026-06-02: Retrieval Evaluation Script Repairs

Updated `eval_retrieval.py`:

1. Load `data/vectors/pharma_docs.meta.json`, the metadata artifact actually written by `step_04_vectorize.py`.
2. Preserve fallback support for legacy `pharma_docs_ids.json`.
3. Compute IDCG from the number of available relevant chunks at rank K so missed relevant chunks reduce NDCG.
4. Deduplicate content and HyDE hits for the same chunk before dense top-k metrics are calculated.

Updated `retrieval_ablation.py`:

1. Use weighted reciprocal rank fusion so Stage 2 and Stage 3 candidates can compete for top-k positions instead of being appended after Stage 1.
2. Disable automatically constructed keyword-search ground truth by default.
3. Add the explicit `--allow-keyword-ground-truth` switch for debugging-only runs.
4. Record ranking and ground-truth policy metadata in new ablation outputs.

Verification:

```powershell
D:\Anaconda3\python.exe -m py_compile .\eval_retrieval.py .\retrieval_ablation.py .\prepare_corpus_staging.py
D:\Anaconda3\python.exe -m unittest discover -s .\tests -p 'test_*.py' -v
D:\Anaconda3\python.exe .\eval_retrieval.py --queries-only
D:\Anaconda3\python.exe .\retrieval_ablation.py --help
```

Result: syntax checks passed; 9 lightweight tests passed; the current query file reports 50 queries and 40 annotated queries. Formal retrieval runs remain blocked on the approved corpus freeze.

## 2026-06-02: Retrieval Candidate Pool

Added `data/eval/annotation_guidelines.md` and `prepare_eval_candidates.py`. The script converts both legacy query files into a new candidate-only artifact and refuses to overwrite an existing candidate pool.

Generated `data/eval/query_candidates_v1.json`:

| Candidate slice | Count |
|---|---:|
| Base candidates | 50 |
| Entity-anchored candidates | 55 |
| Total candidate records | 105 |
| Legacy annotation candidates requiring revalidation | 80 |
| Incomplete legacy candidates | 10 |
| Keyword-search debugging-only candidates | 15 |

The coverage gap is recorded in `data/eval/query_gap_report_v1.md`: document-structure questions and table-evidence questions still need to be created, and scenario coverage must be expanded before final annotation.

## 2026-06-02: Leakage-Free Simulation Core

Updated `agent_sim/simulator.py`, `agent_sim/manufacturer_agent.py`, and `agent_sim/regulator_agent.py`.

### Removed Leakage And Built-In Advantage

1. Weekly disruption progression no longer reads `event.actual_shortage_weeks`.
2. Historical trajectories remain available only in `SimulationResult.compute_metrics()` for evaluation after the run.
3. GraphRAG and no-GraphRAG modes now share the same scenario certification duration.
4. GraphRAG may provide qualification evidence, but retrieval cannot alter the certification mechanics.
5. Sensing is detected from operational state (`capacity < 95%` or shortage severity above 2%), so a no-GraphRAG baseline can reproduce sensing.
6. Regulator exemption notifications now fire when an exemption is first granted instead of checking an unreachable state combination.

### Scenario Mechanics

Added `SimulationScenario` with explicit exogenous parameters:

| Parameter | Meaning |
|---|---|
| `shock_duration_weeks` | Duration of the external disruption |
| `natural_recovery_rate` | Weekly decline in disruption intensity |
| `certification_weeks` | Shared alternate-supplier certification mechanics |

Default profiles depend on disruption type, not historical shortage duration. Future scenario-matrix runs can pass per-event overrides.

### Metrics

The simulation output now includes:

| Metric | Meaning |
|---|---|
| `sde_weeks` | Absolute shortage-duration error |
| `peak_severity_error` | Absolute peak unmet-demand error |
| `trajectory_rmse` | Severity-trajectory RMSE with zero padding |
| `cumulative_unmet_demand` | Simulated severity summed across weeks |
| `sst_timing_error_weeks` | Mean timing error across SST stages |
| `psc` | Pearson severity-trajectory correlation retained for continuity |

Verification:

```powershell
D:\Anaconda3\python.exe -m py_compile .\agent_sim\simulator.py .\agent_sim\manufacturer_agent.py .\agent_sim\regulator_agent.py .\agent_sim\distributor_agent.py .\run_simulation.py
D:\Anaconda3\python.exe -m unittest discover -s .\tests -p 'test_*.py' -v
```

Result: syntax checks passed; 13 lightweight tests passed, including a two-week no-GraphRAG stub simulation with no network access.

## 2026-06-02: Three Simulation Modes

Added `agent_sim/retrieval_modes.py` and updated `run_simulation.py`.

The simulation CLI now exposes:

| Mode | Retrieval access | Purpose |
|---|---|---|
| `llm_only` | None | Pure LLM baseline |
| `flat_rag` | Document FAISS plus chunk JSON only | Retrieval baseline without Neo4j or graph traversal |
| `pharm_graphrag` | Full PharmGraphRAG interface | Proposed method |

`flat_rag` is implemented as an independent adapter. It does not call GraphRAG Stage 1 because the existing Stage 1 already accesses Neo4j entity links. The adapter loads `pharma_docs.faiss`, `pharma_docs.meta.json`, and enriched chunk JSON only.

The old event-level `cert_weeks_llm_guess` and `certification_weeks_needed` fields were removed. Certification mechanics now come only from `SimulationScenario`, making them explicit and shared across comparison modes.

Verification:

```powershell
D:\Anaconda3\python.exe .\run_simulation.py --help
D:\Anaconda3\python.exe -m unittest discover -s .\tests -p 'test_*.py' -v
```

Result: CLI exposes all three modes; 15 lightweight tests passed.

## 2026-06-02: Source Audit And Staging V2

The first local enrichment pilot exposed a source-integrity issue: the configured
`arxiv_supply_chain` URL pointed to arXiv:2305.09617, which is
[*Towards Expert-Level Medical Question Answering with Large Language Models*](https://arxiv.org/abs/2305.09617).
It is unrelated to pharmaceutical supply-chain risk.

The source was removed from `pharma_doc_pipeline/config.py` and excluded from the
formal corpus in `prepare_corpus_staging.py`. The original raw file, the first
staging directory, and the first pilot directory remain preserved for audit.
No canonical artifacts were deleted or replaced.

| Check | Staging v1 | Source-audited staging v2 |
|---|---:|---:|
| Directory | `data/staging/chunks_2026-06/` | `data/staging/chunks_2026-06-v2/` |
| Documents | 33 | 32 |
| Raw chunks | 2,538 | 2,478 |
| Maximum chunk length | 2,271 | 2,271 |
| Excluded documents | 0 | 1 |

## 2026-06-02: Source-Grounded Local Enrichment Pilot

The first pilot used local Ollama `qwen2.5:14b` and made 14 local calls across
9 chunks. It confirmed the local workflow but also showed that the original HyDE
prompt could invent an `ICH Q7` attribution for unrelated excerpts. The bad
arXiv source made this failure especially visible.

Updated `pharma_doc_pipeline/step_03_enrich.py`:

1. Require summaries and table summaries to use only excerpt-supported facts.
2. Permit `[IRRELEVANT_SOURCE]` so unrelated source text can be skipped.
3. Require HyDE questions to use only excerpt- or context-supported regulatory topics.
4. Add document metadata to the C1 prompt.
5. Reject generated questions that mention unsupported authorities or ICH guideline numbers.
6. Version enrichment-cache keys so old prompt responses are intentionally not reused.

The final pilot was written to `data/staging/enrichment_pilot_2026-06-v3/`.

| Check | Result |
|---|---:|
| Model | `qwen2.5:14b` via local Ollama |
| Documents | 3 |
| Chunks | 9 |
| Local LLM calls | 12 |
| Paid API calls | 0 |
| Canonical artifacts replaced | No |
| Manual QA | No cross-document standard-number contamination observed |

Added `tests/test_enrichment_grounding.py`. The full lightweight test suite now
passes 18 tests.

### Updated Enrichment Cost Gate

The source-audited staging corpus contains 32 documents and 2,478 chunks. With
the new prompt versions, legacy enrichment-cache entries are intentionally not
counted as hits:

| Call category | Expected calls | Valid cache hits |
|---|---:|---:|
| Summary generation | 427 | 0 |
| HyDE generation | 2,286 | 0 |
| Table-summary generation | 311 | 0 |
| Total expected local LLM calls | 3,024 | n/a |

The base summary-plus-HyDE lower bound is 2,713 calls. Added
`run_full_local_enrichment_staging.py`, which copies the source-audited chunks
and tables into `data/staging/enrichment_full_2026-06-v1/`, uses deterministic
SHA-256 table-summary cache keys, and supports interrupted-run resumption. The
prepared workspace contains 63 copied files. The local-Ollama enrichment run is
a significant batch job and remains paused for user approval.
