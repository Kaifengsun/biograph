# BM25 Baseline and Corpus-Enrichment Ablation Design

Date: 2026-07-15
Status: Approved

## Objective

Create a second, independent 30-query held-out set and use it to compare a fixed BM25 baseline, four frozen dense-index enrichment variants, a lexical-dense hybrid, and the current hierarchical adaptive method. Update the Chinese manuscript only after human review freezes the gold evidence and all method files are hashed.

## Independence Boundary

The new gold source chunks must not appear as gold evidence in either `data/eval/three_path_evaluation_frozen_2026-07-15.json` or `data/eval/adaptive_text_first_heldout_frozen_run_ready_2026-07-15.json`. Existing HyDE questions, retrieval rankings, provisional semantic candidates, and prior retrieval errors must not be used to draft or select test questions. Candidate source units must be selected from the frozen corpus before any new baseline is executed.

The test set contains 30 questions: 10 single-clause, 8 table, 6 document-structure, and 6 cross-document questions. Supply-chain path questions are excluded because this experiment evaluates text-corpus enrichment rather than structured graph-path recovery.

## Question Construction and Review

Question candidates are drafted directly from previously unused source passages and table records. Each row records a stable review ID, question type, question, proposed gold chunk IDs, source document, headings, and complete source passages. Cross-document questions must have evidence from at least two source chunks and, unless the question explicitly concerns two sections in one guideline, at least two documents.

The review workbook contains a `Review Queue` sheet and an `Evidence Reader` sheet. Reviewers enter `Confirmed`, `Revise`, or `Exclude`. No retrieval rankings or model-suggested alternative chunks are shown. Revised questions require a second confirmation before freezing. Excluded rows are replaced from the unused-source pool until all four quotas are met.

## Compared Methods

`BM25-raw` uses lower-cased alphanumeric tokenization over parent context, heading, and raw source content. Parameters are fixed before evaluation at `k1=1.2` and `b=0.75`; no stemming, query expansion, relevance feedback, or parameter tuning is allowed.

`R1-raw`, `R2-summary`, `R3-HyDE`, and `R4-table` use the existing frozen FAISS indexes under `artifacts/retrieval_ablation/deepseek-v4-pro-v4`. Sidecar vectors map back to source chunk IDs, and duplicate chunk IDs retain their highest-ranked occurrence. Generated summaries, HyDE questions, and table summaries never count as evidence.

`BM25+R4-RRF` combines the source-chunk rankings of BM25 and R4 using RRF with `k=60` and equal weights. `Adaptive-text-first` uses the already locked parameters in `outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json`. No parameter may be changed after the review set is frozen.

## Metrics and Statistical Analysis

All methods report Hit@1, Hit@3, Hit@5, MRR, and nDCG@5 over exact source chunk IDs. Results are reported overall and by query type. The table slice is mandatory.

The preregistered enrichment comparisons are R2 versus R1, R3 versus R2, and R4 versus R3. The preregistered system comparisons are Adaptive-text-first versus BM25-raw and Adaptive-text-first versus BM25+R4-RRF. Query-level bootstrap with 10,000 iterations and seed `20260715` provides 95% confidence intervals. Hit@5 uses the exact paired McNemar binomial test; MRR and nDCG@5 use paired Wilcoxon signed-rank tests. Holm correction is applied within the three metrics of each comparison. Table-slice comparisons are descriptive because `n=8` is underpowered.

## Execution Gate

Before retrieval, the approved workbook is imported into an immutable JSON pack. The pack must contain exactly 30 eligible questions with the declared slice counts, valid chunk IDs, nonempty source passages, and no overlap with previous gold evidence. The question text, corpus, index metadata, BM25 code, evaluator, adaptive code, and parameters are hashed in a method-lock manifest. Retrieval is then executed once.

## Paper Update Rule

Only frozen-run results may enter `sections/draft_chinese_rewritten.md`. The paper must distinguish confirmatory overall comparisons from descriptive small-slice analysis. A component that does not improve the relevant metric must be reported as a null or negative result. The English manuscript remains out of scope until the user accepts the revised Chinese manuscript.

## Risks

Human-authored questions can still share vocabulary with their source passages, which may favor BM25. This is controlled by including conceptual paraphrases and by reporting lexical and dense methods together. The small sample limits statistical power; effect sizes and confidence intervals take precedence over binary significance claims. R3/R4 sidecar vectors may displace exact evidence in flat ranking; this behavior is part of the ablation and must not be repaired after observing test results.
