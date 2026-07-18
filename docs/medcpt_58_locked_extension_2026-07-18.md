# Locked MedCPT Extension on 58 Adjudicated Questions

## Purpose

This feedback-motivated extension tests whether a retrieval-specific biomedical model changes the observed boundary between lexical and semantic retrieval. It is supplementary because the 58-question Gold set had already been used in prior method comparisons. No MedCPT score was observed before the method lock was written and validated.

## Frozen design

- Gold set: 58 independently labelled and jointly adjudicated questions.
- Corpus: 2,478 source chunks from the frozen regulatory corpus.
- BM25 candidates: the previously frozen top 50 for each question.
- Dense method: `ncbi/MedCPT-Query-Encoder` and `ncbi/MedCPT-Article-Encoder`, official exact revisions, zero-shot, CLS representations, unnormalized dot product, query length 64, article length 512.
- Reranking method: `ncbi/MedCPT-Cross-Encoder`, official exact revision, zero-shot, BM25 top 50, maximum length 512.
- Metrics: Hit@1/3/5/50, MRR@50, and binary nDCG@5.
- Uncertainty: 10,000 paired query-level bootstrap samples, seed 20260718.
- Fine-tuning: none.

## Aggregate results

| Method | Hit@5 | MRR@50 | nDCG@5 |
| --- | ---: | ---: | ---: |
| BM25 | 0.948 | 0.820 | 0.800 |
| MedCPT dual encoder, full corpus | 0.345 | 0.300 | 0.246 |
| BM25 top 50 then MedCPT cross-encoder | 0.603 | 0.457 | 0.431 |

For both MedCPT conditions, the paired 95% bootstrap intervals against BM25 were below zero on all three displayed metrics. The direction also held in the single-clause, table, document-structure, and cross-document slices.

## Interpretation boundary

MedCPT was trained from PubMed search logs, where article-level topical relevance is central. The present task asks whether a short regulatory passage directly supports a specific answer, often using exact guideline identifiers, table labels, and defined phrases. These results do not show that biomedical semantic models are generally ineffective. They show that MedCPT's zero-shot relevance function did not transfer to this clause-level regulatory evidence task.

## Audit pointers

- Lock SHA-256: `0e240b7d4fffa504a800948c61a355a7ed63ab6afeeebf1f3457f90bd1e597e6`
- Evaluation SHA-256: `6f403010fa14428bc64b2be96a931793dfac152f2170d451bd81a83f3a80a409`
- Local lock: `outputs/medcpt_58_2026-07-18/method_lock.json`
- Local evaluation: `outputs/medcpt_58_2026-07-18/evaluation.json`
- Reproduction code: `tools/medcpt_58/`

Large inference rankings, model weights, and source-bearing payloads remain outside the public repository.
