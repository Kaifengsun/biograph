# Overleaf Manuscript Package

This directory contains the English project-group review draft for the pharmaceutical regulatory evidence retrieval study.

## Build

The project uses a portable `article` layout, BibTeX, and no shell escape. On Overleaf, set the compiler to pdfLaTeX and compile `main.tex`. A local build uses:

```text
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## Evidence status

The principal holdout, enrichment ablation, selective-reranking confirmation, double annotation, adjudication, and 58-query formal evaluation were completed before this English draft. The Qwen3-Reranker-0.6B comparison was locked after the formal evaluation and is explicitly reported as supplementary and post hoc.

`citation_audit.csv` records the authoritative verification page and supported claim for every bibliography entry. `validation/` contains machine-readable checks. Source-bearing candidate files, review workbooks, copyrighted PDFs, model weights, and API credentials are intentionally excluded.

## Figures

Figures are intentionally deferred until the project group reviews the scientific narrative. The source compiles without missing figure files. Once the narrative is accepted, the next revision can add a corpus-and-retrieval workflow figure and one results figure without restructuring the text.

## Submission fields

Before journal submission, resolve the funding statement, the institutional or journal treatment of external annotation, acknowledgement consent, and the target venue's authorship and AI-assistance policies.
