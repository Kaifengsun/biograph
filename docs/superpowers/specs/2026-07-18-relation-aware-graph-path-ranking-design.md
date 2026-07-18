# Relation-Aware Graph Path Ranking: Design Specification

## Status and scope

This is a feedback-driven supplementary experiment. It was designed after the
main text-retrieval evaluation and after project-group feedback requested a
deeper graph assessment. It is not a preregistered or confirmatory comparison.
The experiment evaluates whether relation direction and relation semantics help
rank auditable graph paths; it does not treat graph nodes as source passages and
does not alter any reported passage-retrieval Gold labels.

The frozen graph is
`artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda`
(7,578 nodes, 15,237 directed edges). The evaluation pool contains 30
independently reviewed questions: 10 shortage chains, 10 drug/API/supplier
chains, and 10 regulatory-logic chains. Joint adjudication ended with one
originally confirmed regulatory question, five wording revisions that retain
their paths, and no exclusions or unresolved decisions.

## Approaches considered

1. **Transparent relation-aware ranking (selected).** Generate bounded paths and
   score relation direction, question-to-relation cue agreement, node-text
   agreement, and provenance completeness. This is auditable and suitable for a
   30-question set.
2. **Supervised path ranker (rejected).** Thirty questions are insufficient for
   credible training and held-out model selection; leakage and overfitting would
   dominate the result.
3. **LLM path selection (not a primary condition).** An LLM could narrate path
   choice, but stochasticity and prompt sensitivity would weaken the clean
   comparison requested by the feedback.

## Frozen Gold construction

The original independent Reviewer A and Reviewer B workbooks remain immutable.
The six-row final consensus workbook is stored privately because it contains
audit annotations. A deterministic finalization script will produce a
machine-readable 30-question ledger containing:

- final question wording;
- accepted node sequence and directed edge sequence;
- answer and provenance sources;
- original reviewer labels and adjudication resolution;
- hashes of the graph files, registry, both returned review files, and final
  consensus workbook.

For the 24 questions without status disagreement, the original reviewed
question and path are retained. For the six adjudicated questions, final wording
and answers come from the consensus workbook. A `Revise` decision means that the
revised question and unchanged supported path enter Gold; it is not a rejection.

## Candidate generation

Candidate generation must not receive the Gold target node or Gold edge
sequence. Query anchors are detected only by normalized exact or alias matching
between question text and frozen node names/identifiers. If multiple anchors
match, all are retained. From each anchor, the generator enumerates directed
simple paths of one to three hops. Incoming traversal is disabled in the primary
experiment because direction is part of the evaluated semantics.

Administrative hierarchy relations (`NEXT`, `SUMMARIZES`, `CONTAINS`,
`PARENT_OF`, `HAS_SECTION_SUMMARY`, and `HAS_DOCUMENT_SUMMARY`) are excluded
unless they are explicitly cued by a question. This prevents thousands of
document-navigation edges from crowding out supply-chain and regulatory
relations. Duplicate node-and-relation sequences are collapsed. A deterministic
lexicographic order breaks all remaining ties. Candidate count and Gold-path
coverage are reported for every query. A question with no detectable anchor or
no generated Gold path remains in the denominator and is reported as a candidate
generation failure.

## Compared ranking conditions

### B0: untyped bounded traversal

The baseline ranks candidates by hop count, then by the stable lexicographic
path identifier. It ignores relation names, question wording, node names, and
provenance. This represents basic bounded graph traversal rather than a learned
or semantic reasoner.

### B1: node-text ranking

This diagnostic condition adds token overlap between the question and candidate
node names/properties but still ignores relation labels. It separates gains from
identifying relevant entities from gains due specifically to relation semantics.

### R1: relation-aware ranking

The selected method uses a fixed additive score with components that are saved
before evaluation:

- relation-cue agreement between normalized question phrases and relation
  aliases;
- direction agreement for asymmetric relation cues;
- node-text overlap;
- provenance completeness for every edge;
- a small length prior favouring the shortest path that satisfies the cues;
- penalties for an uncued relation and for reversed asymmetric semantics.

Relation aliases are derived from relation names and a manually declared,
domain-transparent lexicon (for example `supersedes`, `complements`,
`supplied by`, `active ingredient`, `reported by`, and `affects NDC product`).
No weights or aliases may be changed after aggregate or per-question scores are
observed. Exact weights, aliases, graph hashes, Gold hashes, and software version
are written to `method_lock.json` before the evaluation command runs.

## Metrics and analysis

The primary metrics are exact accepted-chain Hit@1, Hit@3, Hit@5, and MRR. A
candidate is correct only when its directed node and relation sequence matches
an accepted Gold path. Candidate-generation recall is reported separately so a
ranking gain cannot hide missing candidates. Results are reported overall and
for the three prespecified categories.

Paired query-level differences compare R1 against B0 and B1. Because the pool is
small and was created from the frozen graph, the analysis emphasizes exact
counts, paired bootstrap confidence intervals, and failure categories rather
than significance claims. The report must disclose that questions were designed
to exercise known graph relations and therefore do not estimate performance on
arbitrary unseen graph questions.

## Leakage controls and failure handling

- Candidate generation cannot access `edges`, `nodes`, `draft_answer`, or final
  answer fields from the Gold registry.
- Evaluation code receives Gold paths only after candidate rankings have been
  serialized.
- Method-lock and inference files are separate; hashes verify both.
- Missing provenance, duplicate identifiers, malformed edges, anchor failures,
  and candidate-cap truncation fail loudly or appear as explicit error records.
- Original review workbooks and final consensus are never overwritten.
- The experiment does not modify canonical graph artifacts.

## Deliverables

- final 30-question Gold ledger and integrity manifest;
- `method_lock.json` written before score inspection;
- candidate rankings for B0, B1, and R1;
- aggregate, category, paired-bootstrap, and failure-analysis JSON/Markdown;
- focused unit tests for finalization, anchor detection, path enumeration,
  direction scoring, and metric calculation;
- a concise manuscript update that labels the experiment supplementary and
  feedback-driven.
