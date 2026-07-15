# Enrichment Quality Audit

Date: 2026-06-10  
Audited artifact: `data/staging/enrichment_full_2026-06-v1/`  
Model: local Ollama `qwen2.5:14b`  
Status: conditional pass for moving toward corpus freeze. Do not rebuild final indexes until the minor clean-up items below are handled.

## Executive Decision

The full local enrichment output is structurally complete and broadly usable for the next experimental stage. The run produced complete enriched artifacts for all 32 source-audited documents, with no paid API calls and no canonical artifact replacement.

The main risks are not catastrophic hallucination or incomplete output. They are smaller indexing-time quality issues:

1. A few HyDE questions contain Chinese fragments.
2. Some HyDE questions are intentionally scenario-like but over-speculative for strict evidence retrieval.
3. Many table summaries describe document history/revision tables, which are valid but low-value for the retrieval experiment.
4. One extracted table row has no generated summary and appears malformed.

Recommended decision: proceed to a light remediation/filtering pass, then corpus freeze. A full rerun is not justified.

Machine-readable remediation candidates were written to:

`data/staging/enrichment_full_2026-06-v1/_enrichment_remediation_candidates.json`

## Artifact Completeness

| Check | Result | Assessment |
|---|---:|---|
| Enriched documents | 32/32 | Pass |
| Enriched chunks | 2478 | Pass |
| Chunks with `enrichment_meta` | 2478/2478 | Pass |
| Empty chunks | 0 | Pass |
| Excluded `arxiv_supply_chain` present | 0 | Pass |
| Table rows | 312 | Pass |
| Table rows with summary | 311/312 | Minor gap |
| Table-summary coverage | 99.68% | Pass |
| Paid API calls | 0 | Pass |
| Canonical artifacts replaced | false | Pass |

Verification tests:

```powershell
D:\Anaconda3\python.exe -m unittest discover -s tests -p "test_enrichment*.py" -v
```

Result: 9 enrichment-related tests passed.

## Enrichment Coverage

| Metric | Count |
|---|---:|
| Summary-eligible chunks | 427 |
| Generated summaries | 406 |
| HyDE-eligible chunks | 2286 |
| Chunks with HyDE questions | 2156 |
| HyDE questions generated | 4247 |
| C1 chunks | 1364 |
| C2 chunks | 922 |
| C1/C2 strategy mismatches | 0 |
| Chunks below 100 chars with HyDE | 0 |
| Unsupported named-reference questions filtered | 119 |
| Unsupported named-reference leaks after recheck | 0/4247 |

The C1/C2 split is internally consistent. The named-reference filter also appears effective: all retained HyDE questions passed the same support check used during generation.

## Quality Findings

### 1. Source-grounding filter worked

The pipeline filtered 119 unsupported named-reference questions. A post-run recheck over all 4247 retained HyDE questions found 0 unsupported named-reference leaks.

This matters because the earlier pilot showed a risk of invented document attributions. The current `v3_doc_meta_filter` behavior appears to control that risk.

### 2. Missing outputs are mostly explainable

There are 21 summary-eligible chunks without summaries and 130 HyDE-eligible chunks without HyDE questions. The top missing-HyDE documents are table-heavy or reference-heavy documents, especially `ich_q3d_r2` and `ich_q3c_r9`.

Common causes observed in samples:

| Pattern | Example |
|---|---|
| References/bibliography chunks | ICH Q3C and Q3D reference sections |
| Page-number residue | `ich_q1_draft_2025_C0211_4afd1b38` |
| Copyright/front matter | WHO EML license pages |
| Table fragments | Matrixing and example table chunks |
| Unsupported named references filtered to zero | Some ICH M7 and ICH Q14 chunks |

These skips are mostly acceptable, but a few valuable chunks may deserve a later targeted repair pass if they are selected as evaluation evidence.

### 3. HyDE questions are useful but need light filtering

Observed strengths:

- Many questions are specific to regulatory risk and supply-chain decision contexts.
- C1 questions are generally grounded in long chunk content.
- C2 questions use short-chunk context without obvious unsupported document references.

Observed risks:

| Risk | Count | Action |
|---|---:|---|
| CJK fragments in generated outputs | 8 | Remove or regenerate these individual questions. |
| Very long HyDE questions over 260 chars | 79 | Consider keeping for retrieval or trimming during index build. |
| Scenario/speculation terms such as import alert, production halt, shortage | 1032 questions | Not automatically wrong, but should be tagged as scenario-oriented. |
| Duplicate HyDE questions within a chunk | 0 | No action. |
| `[IRRELEVANT_SOURCE]` leaked into outputs | 0 | No action. |

Example CJK issue:

`fda_cgmp_guidance_C0015_3a3a3e7d` generated a mostly English question ending with Chinese text: `不合格的操作和产品质量问题`.

Example over-speculative phrasing:

Several questions ask whether manufacturers may face `import alerts` or `production halts`. This is useful for supply-chain scenario retrieval, but may be too strong for strict regulatory-clause retrieval unless the source chunk supports those enforcement outcomes.

### 4. Table summaries are nearly complete but need usefulness filtering

Only one table lacks a summary:

| Field | Value |
|---|---|
| File | `ich_q3e_draft_tables.json` |
| Index | 3 |
| Chunk ID | `ich_q3e_draft_C0093_8a2edce2` |
| Reason | The table text appears malformed/OCR-damaged. |

Preview:

```html
<table><tr><td>Scenario 4: bextowtheir apicabe thtyihlichle ACTOTor compound-specific AI/PDE) ...</td><td>Components may be considered qualified without additional extractables or leachables testing.</td></tr></table>
```

This is not a blocker. It should either be excluded from the table index or manually repaired if Q3E extractables/leachables scenarios become important for evaluation.

The larger issue is table usefulness. The audit identified many history/revision/codification tables. They are valid summaries, but low-value for the retrieval experiment and may pollute table-aware retrieval.

Recommendation: during table-index construction, tag or exclude tables whose content is dominated by `Code`, `History`, `Date`, `Approval`, `Steering Committee`, or `public consultation`, unless the query explicitly asks about document history.

## Sample Checks

| Sample | Finding |
|---|---|
| `ich_q7_C0040_5c7114c0` | HyDE questions correctly focus on receipt, quarantine, labeling, tampering, and material identification. |
| `ich_q13_C0020_401ae290` | Summary accurately captures scale-out, equipment duplication, traceability, and control-strategy modification. |
| `ich_q2r2_C0010_16ae729b` | C2 questions are plausible for analytical procedure lifecycle and acceptance criteria. |
| `ich_q1a_C0015_191e4ad8` table | Summary accurately captures long-term, intermediate, and accelerated storage conditions. |
| `who_eml_2023_C0009_37c9a8b6` table | Summary correctly describes anaesthetics, preoperative medicines, gases, dosage forms, and routes. |
| `who_stability_q1f_C0017_1c6557ce` table | Summary accurately captures stability storage conditions and minimum submission periods. |

## Recommended Remediation Before Freeze

1. Remove or regenerate the 8 HyDE questions containing CJK fragments.
2. Add an index-time flag for `scenario_oriented_hyde` questions when they mention enforcement, production halt, import alert, or shortage.
3. Add a table-usefulness filter before building the table-summary index.
4. Exclude or manually repair the malformed `ich_q3e_draft` table row.
5. Keep the 21 missing summaries and 130 missing HyDE sets as acceptable unless a selected evaluation query depends on one of those chunks.

## Recommendation

Proceed, but with a small clean-up pass first.

The enrichment is strong enough to serve as the basis for the frozen experiment corpus. The problems found are localized and can be addressed without rerunning the full model job. After remediation, the next step should be a clearly gated corpus freeze followed by separate index builds for the retrieval ablation matrix.
