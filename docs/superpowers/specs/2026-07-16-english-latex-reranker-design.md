# English LaTeX Manuscript and Modern Reranker Design

## Objective

Produce an English, text-complete LaTeX manuscript that can be uploaded to
Overleaf and sent to the paper programme for an initial editorial assessment.
The revision will strengthen three areas without changing the evidential scope
of the study:

1. expand and verify the literature base;
2. reorganize the narrative around task separation and empirically observed
   design boundaries; and
3. add one fixed modern neural reranking baseline.

Figures are out of scope for this phase. The manuscript will contain figure
placeholders and captions only where they help the project group understand the
intended final presentation.

## Author Metadata

- Author: Kaifeng Sun
- Affiliation: China Jiliang University, Hangzhou, China
- Correspondence email: `2300702216@cjlu.edu.cn`
- Authorship: sole author and corresponding author

The manuscript will not mention the Cambridge course, publication guarantee,
or Professor Nektarios Oraiopoulos unless a later factual contribution creates
an appropriate acknowledgement obligation. It will not claim that China
Jiliang University endorsed the findings.

## Narrative Design

The paper will not be presented as a new retrieval algorithm that beats the
state of the art. Its central claim is a task and system design result:

> Verbatim regulatory-source retrieval and structured pharmaceutical supply
> fact verification are non-interchangeable evidence tasks. Within the
> evaluated corpus, relevance protocol, 58-query adjudicated set, and compared
> methods, lexical retrieval was the strongest default ranker for regulatory
> passages; document hierarchy supported navigation and context recovery; and
> graph paths were more appropriately evaluated as a separate,
> provenance-bearing channel for structured facts.

The English manuscript will be written directly in academic English rather
than translated sentence by sentence. The argument will follow this order:

1. regulatory evidence creates two distinct retrieval obligations;
2. a source-preserving corpus and heterogeneous evidence graph provide the
   necessary representation;
3. the system tests bottom-up, top-down, dense, enriched, fused, and graph
   retrieval choices;
4. originally locked and adjudicated experiments characterize where added
   complexity helped, failed, or needed separate evaluation in this study; and
5. the negative results motivate a study-specific design implication rather
   than a generally validated prescription or algorithmic superiority claim.

## Modern Reranker Baseline

### Model and Candidate Flow

The only new supplementary post-hoc reranking condition will be
`Qwen/Qwen3-Reranker-0.6B`, used as a fixed off-the-shelf generative
cross-encoder. It was selected before any neural score was produced because it
is a newer Apache-2.0 multilingual reranker of the same 0.6B scale as the
originally considered BGE model and is feasible on the available local GPU. It
will rerank the top 50 candidates returned by the existing context-matched BM25
index:

```
query -> context-matched BM25 top 50 -> Qwen3 reranker -> top 5 evaluation
```

The machine-readable output retains the complete reranked top-50 list for each
query. Top 5 is the main presentation depth, not the stored ranking depth;
MRR@50 and candidate diagnostics are computed from the retained top 50.

The reranker input will contain the same source-chunk payload used by the
existing source-level evaluation. Generated summaries, HyDE questions, graph
nodes, and method labels will not be inserted into the reranker input. Ties
will be resolved deterministically by the original BM25 rank and chunk ID.

### Locked Configuration

- model: `Qwen/Qwen3-Reranker-0.6B`
- candidate depth: 50
- output depth: 5
- instruction: `Given a pharmaceutical regulatory question, retrieve a source passage that directly supports the answer.`
- score: normalized probability assigned to `yes` versus `no` by the official reranking prompt
- no fine-tuning
- no threshold optimization
- no query-type gate
- no parameter selection on the 58-query set
- deterministic inference where supported

Before inference, a machine-readable lock manifest and the implementation that
consumes it must be committed. The lock must record:

- the exact model repository revision and downloaded-file hashes;
- tokenizer revision, maximum sequence length, and truncation policy;
- query--passage serialization, field order, and Unicode normalization;
- candidate ordering and deterministic tie-breaking;
- corpus, index, query, qrels, and candidate-list hashes;
- dependency versions, device, precision, batch size, seeds, and deterministic
  runtime settings;
- all metrics, cutoffs, bootstrap settings, and analysis code version; and
- the exact execution command and output locations.

The official Qwen ModelScope repository is used as the domestic download
source because the attempted Hugging Face mirror redirected to the original
Hub and failed before any model score was produced. ModelScope's `master`
revision name is not treated as immutable: the lock records every downloaded
file's SHA-256 digest and the aggregate manifest hash, and inference refuses to
run if any local model file differs.

The run follows a one-shot reporting rule: every valid result and every
prespecified metric is retained regardless of direction. After reranker scores
on the 58 queries have been inspected, the model, preprocessing, payload,
truncation, candidate depth, configuration, metrics, and reporting decisions
may not be changed. A failed run caused solely by infrastructure may be resumed
from logged checkpoints without changing the locked computation.

If the model cannot run locally because of an irreducible runtime or memory
constraint, the experiment will stop and report the failure. It will not be
silently replaced with a different model. Any replacement requires a new
documented decision.

### Evaluation Status

The jointly adjudicated 58-query set has already been observed. Therefore the
new reranker comparison is **post hoc and supplementary**, not confirmatory.
The manuscript, table captions, and supplement must use that designation and
must not describe it as preregistered, prospectively locked, or an independent
confirmation. Its purpose is an exploratory sensitivity analysis of whether a
fixed neural cross-encoder improves ordering *within BM25's top-50 candidate
pool*. It cannot evaluate modern first-stage neural retrieval and cannot
recover a relevant chunk that BM25 did not retrieve in its top 50.

The comparison will report BM25 candidate recall/Hit@50 as the reranker's
attainable recall ceiling, followed by Hit@1, Hit@3, Hit@5, MRR@50, and
binary-gain nDCG@5 over all adjudicated Gold chunks. MRR@50 is the reciprocal
rank of the first Gold chunk within ranks 1--50 and is zero when no Gold chunk
occurs in that range. BM25 and the reranker use this identical cutoff in paired
comparisons. Queries are the pairing and resampling unit. Exploratory
percentile intervals will use 10,000 paired query-bootstrap replicates with
seed 20260716. Deterministic ties use original BM25 rank and then chunk ID.
Paired metric differences from BM25 will be reported, but the intervals are
descriptive resampling uncertainty and will not support confirmatory
significance language. Slice results may be reported descriptively, but no
slice-based inferential or superiority claim is allowed.

## Literature Expansion and Verification

The target bibliography is approximately 25--35 references organized around:

1. pharmaceutical regulatory science and digital evidence;
2. drug-shortage data and supply-risk evidence;
3. lexical, dense, and neural reranking methods;
4. retrieval-augmented generation and HyDE;
5. hierarchical and graph-based retrieval;
6. biomedical or medical RAG and evidence grounding; and
7. reliability, provenance, and evaluation of medical information retrieval.

Every cited work, including the nine existing references, must be verified
against at least one authoritative metadata source: a publisher proceedings or
journal page, Crossref DOI record,
PubMed, arXiv record for an explicitly identified preprint, or an official
regulatory publication. Where available, DOI metadata will be checked against
the publisher page. The audit will separately record (a) bibliographic metadata
verification and (b) a support decision for every distinct manuscript claim
attached to each citation occurrence. Reuse of one source for materially
different claims requires separate audit rows. The audit will also record
publication status, version of record, known correction or retraction status,
and, for regulatory sources, the authoritative version and effective or
publication date. Search-result snippets, generated research reports,
Academia.edu pages, and unverifiable citation lists are discovery aids only and
cannot serve as final metadata sources.

The bibliography must not:

- invent or normalize a title without verification;
- cite a preprint as a peer-reviewed article;
- report a venue, year, volume, page range, DOI, or indexing status that has
  not been checked;
- use the internal `filecite` or `turn...` markers from generated reports; or
- add a work solely to increase the reference count.

A machine-readable citation audit will record the verification source and
claim-support decision for every distinct citation-backed claim. Only verified
entries will enter `references.bib`.

## LaTeX Deliverable

The Overleaf-ready package will use a neutral `article` layout until the target
journal is chosen. The intended structure is:

```
paper/
  main.tex
  references.bib
  citation_audit.csv
  sections/
    01_introduction.tex
    02_related_work.tex
    03_task_definition.tex
    04_data_and_graph.tex
    05_methods.tex
    06_experiments.tex
    07_results.tex
    08_discussion.tex
    09_conclusion.tex
  tables/
  supplementary.tex
  README.md
```

`main.tex` will contain the title, author and affiliation, abstract, keywords,
section includes, bibliography, and declarations. Bibliography processing will
use BibTeX with a portable style bundled or named in the README. The README
will document the LaTeX engine, exact build command, artifact provenance, and
the distinction between previously locked and adjudicated analyses and the
supplementary post-hoc reranker. Generated tables will be included from
`tables/`; figure
placeholders will be text boxes or comments that cannot create missing-file
errors or carry claims that are unintelligible without a figure.

The main text will include only results traceable to existing frozen artifacts
or the new reranker output. The supplementary material will hold detailed
annotation protocol, method-lock information, secondary metrics, and audit
details that would interrupt the main narrative.

The package will compile without shell escape and without proprietary fonts.
It will avoid journal-specific commands so it can later be adapted to TIRS or
another target without rewriting the manuscript body.

## Statements and Research-Ethics Boundaries

The project-group review draft will include carefully bounded statements, or
clearly identified administrative fields outside the scientific prose, for:

- sole-author CRediT contributions;
- funding;
- competing interests;
- data and code availability;
- use of public regulatory documents and databases; and
- acknowledgement or authorship treatment of the external domain reviewer,
  subject to documented assessment, the reviewer's consent, and the target
  journal's authorship policy.

The manuscript will state that no patient-level or clinical participant data
were used. It will not assert that the work is exempt from human-participant
review merely because the source corpus is public: the status of the external
expert annotation will be checked against institutional and target-journal
policy before submission.

Before editorial submission, the author will document whether the external
reviewer contributed to annotation design, adjudication, interpretation,
drafting, final approval, or accountability. That record will be assessed under
the target journal's authorship criteria. A person will not be named in an
acknowledgement without consent. CRediT roles, funding, competing interests,
data/code availability, acknowledgement, and ethics language must be resolved
before editorial submission, even if the earlier project-group review copy
marks an administrative field as pending confirmation.

## Validation and Acceptance Criteria

The implementation will provide the following checkers. Each checker returns
exit code 0 only when every check passes and writes its named JSON report under
`paper/validation/`:

- `validate_lock.py` checks schema, hashes, frozen settings, model revision,
  and one-shot authorization (`lock_report.json`);
- `validate_results.py` checks 58-query completeness, recomputes metrics and
  paired BM25 differences, and verifies artifact hashes
  (`results_report.json`);
- `validate_citations.py` checks BibTeX fields, duplicates, metadata sources,
  publication status, and occurrence-level claim support
  (`citation_report.json`);
- `reconcile_numbers.py` checks the empirical-number manifest against source
  artifacts (`number_report.json`);
- `validate_manuscript.py` checks prohibited language, post-hoc labels,
  includes, missing tables, TODOs, and unresolved references
  (`manuscript_report.json`); and
- `scan_public_package.py` checks secret patterns, environment-variable values,
  local absolute paths, disallowed review-workbook names, source-passage
  fingerprints, and a public-file allowlist (`public_package_scan.json`); and
- `run_all_checks.py` invokes all checkers and the documented LaTeX build,
  returning nonzero if any component fails (`validation_summary.json`).

The empirical-number manifest is limited to reported corpus, graph,
annotation, retrieval, uncertainty, and statistical quantities. Each record is
keyed by manuscript file and line anchor, displayed value, source artifact,
JSON/CSV field or formula, tolerance, and checker status. It excludes years,
section numbering, citation metadata, model names, and mathematical constants.

Raw reranker logits may differ across supported hardware by at most absolute
and relative tolerance `1e-5`, locked before inference. Candidate IDs,
rankings, per-query metric values, and rounded aggregate values must reproduce
exactly; otherwise the clean-environment check fails.

The phase is complete when:

1. the reranker run is reproducible from a committed script, lock manifest,
   dependency record, exact command, runtime log, and input/output checksums;
2. all reported numbers match machine-readable result artifacts;
3. every cited work has recorded metadata and claim-support verification and
   passes duplicate, required-field, publication-status, and retraction checks;
4. `pdflatex -> bibtex -> pdflatex -> pdflatex`, as documented in the README,
   completes with zero errors and zero undefined citation/reference warnings;
5. `supplementary.tex` and all generated tables are included and compile;
6. `scan_public_package.py` passes and the versioned manual content-release
   checklist confirms that no API key, local credential, private review
   passage, personal information, or copyrighted full text is included in the
   public package;
7. `reconcile_numbers.py` maps every in-scope empirical quantity to its
   machine-readable artifact and reports no mismatch;
8. automated checks find no unresolved scientific-prose TODOs, missing tables,
   or unqualified uses of `confirmatory`, `preregistered`, `independent
   confirmation`, or superiority language for the reranker;
9. every manuscript and table occurrence of the reranker labels it
   supplementary and post hoc, and all 58 queries and prespecified metrics are
   retained in its machine-readable output;
10. a clean-environment reproduction check records the device and numerical
    tolerance when exact floating-point equality is unavailable; and
11. the abstract, introduction, results, discussion, and conclusion pass a
    claim-consistency audit and remain intelligible without future figures.

Automated gates are necessary but not sufficient for item 11. A versioned
semantic checklist will record claim scope, post-hoc wording, cross-section
consistency, and readability. Kaifeng Sun is the named final approver; project
group comments are external advisory review and are logged separately.
The same checklist contains a manual public-package review for private passages,
copyrighted full text, personal information, and credentials that automated
patterns cannot reliably detect. Kaifeng Sun is also the final approver for
that content-release decision.

## Non-Goals

This phase will not:

- reproduce a broad SOTA leaderboard;
- tune a new method on the 58-query set;
- claim that graph retrieval improves passage ranking;
- claim prediction of shortage duration or causal impact;
- add new figures before the project group reviews the text;
- select a final journal template; or
- upload source-bearing review workbooks or private data to GitHub.
