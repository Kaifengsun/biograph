# Relation-Aware Graph Evidence-Chain Ranking: Design Specification

## Status and scope

This is a feedback-driven **exploratory** supplementary experiment designed
after the main text-retrieval evaluation and project-group feedback. It is not a
preregistered or confirmatory comparison. Because the investigators had already
seen the questions and reviewed chains before this design was locked, no result
will be described as blind or confirmatory. The lock prevents tuning after
scores, not knowledge of the evaluation pool during initial method design.

The frozen graph is
`artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda`
(7,578 nodes, 15,237 directed edges). The pool contains 30 independently
reviewed questions: 10 shortage chains, 10 drug/API/supplier chains, and 10
regulatory-logic chains. Joint adjudication ended with one originally confirmed
regulatory question, five wording revisions that retain their chains, and no
exclusions or unresolved decisions.

The experiment evaluates whether relation cues and edge direction help rank
auditable graph evidence chains. It does not treat graph nodes as source passages
and does not alter passage-retrieval Gold labels.

## Approaches considered

1. **Transparent relation-aware ranking (selected).** Enumerate bounded evidence
   chains and score relation cues and direction with fixed equations.
2. **Supervised path ranker (rejected).** Thirty questions are insufficient for
   credible training and model selection.
3. **LLM path selection (not primary).** Prompt sensitivity and stochasticity
   would weaken the requested controlled comparison.

## Gold finalization and public audit layer

The original Reviewer A and Reviewer B workbooks remain immutable. A
deterministic finalizer produces a 30-question ledger containing final wording,
accepted canonical directed edge triples, accepted nodes, answer, provenance,
review resolution, and hashes of the graph, registry, returned reviews, and
final consensus workbook. For 24 questions without a status disagreement, the
reviewed wording and chain are retained. For the six adjudicated questions,
final wording and answers come from the consensus workbook. `Revise` means that
the revised question and unchanged supported chain enter Gold.

A sanitized public adjudication ledger discloses final wording, accepted edge
triples and nodes, final status, and whether wording changed. Reviewer identities,
free-text notes, and local paths are omitted. It is sufficient to rerun evaluation
from the finalized Gold layer. Hashes and an access-on-request audit statement
link it to the private workbooks.

## Sanitized inference input and Gold isolation

Finalization writes two physically separate inputs. `inference_queries.json`
contains only question ID, category, original wording, final wording, and a
wording-changed flag. It contains no answer, target, node, edge, reviewer,
adjudication, or Gold field. Candidate generation and ranking commands can read
only this sanitized file, the frozen graph, and `method_lock.json`. Evaluation
is a separate command that joins serialized rankings to the Gold ledger. Tests
fail if forbidden Gold keys occur in inference input.

The method is committed after the Gold ledger because this is explicitly an
exploratory feedback response. After `method_lock.json` is written, aliases,
weights, graph projection, normalization, cap, and tie-breaking cannot change.
A sensitivity run uses the five original and five revised wordings under the
same lock and is descriptive only.

## Candidate generation

The retrieval unit is a rooted connected **evidence chain**, not necessarily a
linear path. Accepted chains may branch to several suppliers or references. A
chain contains one to five canonical directed edge triples and their incident
nodes. Gold fields are unavailable to the generator.

### Fixed task-graph projection

All conditions share one query-independent projection containing:
`AFFECTS_NDC_PRODUCT`, `REPORTED_BY`, `HAS_ACTIVE_INGREDIENT`, `CONTAINS_API`,
`SUPPLIED_BY`, `COVERS_TOPIC`, `SUPERSEDES`, `USES_PRINCIPLES_FROM`,
`COMPLEMENTS`, `INTERPRETS`, `APPLIES_DEFINITION_FROM`, and
`REQUIRES_COMPLIANCE_WITH`. This is a declared task boundary, not a per-question
semantic filter. Results estimate ranking inside a supply/regulatory evidence
view, not arbitrary search over all graph edges. An unfiltered one- and two-edge
coverage diagnostic is reported separately and is not a ranking condition.

### Anchor normalization

Text is Unicode NFKC-normalized, lowercased, and split on non-alphanumeric
characters. Hyphens, underscores, slashes, and parentheses become spaces.
Aliases are built without Gold from node `name`, the suffix of node `id`, and
allowlisted scalar properties: `doc_id`, `package_ndc`, `generic_name`,
`ingredient_name`, `company_name`, `reference_name`, `topic_name`, and `cas`.
Aliases shorter than three characters are discarded. Token-bounded exact
matches are found in each question; contained matches are removed in favour of
the longest span. Every node sharing a surviving alias is retained, so alias
collisions are not resolved using Gold. Anchors are sorted by alias token count
descending, alias length descending, then node ID. At most 64 anchors are kept;
truncation is logged.

### Enumeration and identity

Projection edges are traversable in either direction during enumeration, while
canonical source and target are preserved as features. Starting from each
anchor, deterministic breadth-first expansion adds one edge incident to any node
already in the partial chain, rejects repeated canonical triples and cycles that
add no node, and emits every connected chain of one to five edges. The sole
exception is a parallel edge with a different relation between a node pair
already joined in the chain; this preserves multi-relational evidence such as
one guideline being both a principles source and a definitions source. Adjacency
and expansion are sorted by `(relation, source, target)`. Anchors are processed
round-robin. The deterministic cap is the first 50,000 unique chains per
question. There is no wall-clock truncation. A platform-independent safety limit
of 2,000,000 attempted edge additions aborts the entire query as failed rather
than scoring a partial result. Retained counts, cap/abort flags, attempted
expansions, and per-anchor counts are recorded.

A candidate signature is the lexicographically sorted set of canonical
`(source, relation, target)` triples; traversal order and edge-instance IDs are
not part of identity. Parallel edges with the same triple are merged and their
provenance records are unioned by canonical JSON hash. Duplicates generated from
multiple anchors are collapsed; scoring uses the maximum feature value over
their valid anchor traversals. Gold matching uses the same triple-set identity.
A question with no anchor or no generated Gold chain remains in every metric
denominator and is an explicit candidate-generation failure.

## Compared conditions

### B0: untyped bounded traversal

B0 ranks by edge count, then signature. It ignores relation names, question
wording, node names, direction, and provenance.

### Feature definitions

Question and node tokens use anchor normalization plus a fixed English stop list
stored in the lock. Candidate node text is the union of aliases for incident
nodes. `F1tok(q,c)` is set-token F1 between non-stopword question tokens and
candidate node tokens. `Prov(c)` is the fraction of canonical triples for which
at least one merged edge record has a nonempty provenance object. Let `m` be edge
count. The matched relation-blind score is:

`Core(q,c) = 1.00*F1tok(q,c) + 0.10*Prov(c) - 0.02*(m-1)`.

The normative relation alias map is:

- `AFFECTS_NDC_PRODUCT`: `affects ndc product`, `package ndc`, `ndc product`;
- `REPORTED_BY`: `reported by`, `company reported`, `reported`;
- `HAS_ACTIVE_INGREDIENT`: `has active ingredient`, `active ingredient`,
  `ingredient`;
- `CONTAINS_API`: `contains api`, `linked api`, `api is linked`;
- `SUPPLIED_BY`: `supplied by`, `manufacturers supply`, `manufacturer supply`,
  `suppliers`, `supplier`;
- `COVERS_TOPIC`: `covers topic`, `topic does`, `topic is`, `linked topic`;
- `SUPERSEDES`: `supersedes`, `superseding`, `replaces`, `replacement`;
- `USES_PRINCIPLES_FROM`: `uses principles from`, `source of principles`,
  `principle dependencies`, `supplies principles`, `foundation`;
- `COMPLEMENTS`: `complements`, `complementary`, `complement`;
- `INTERPRETS`: `interprets`, `interpreted by`, `interpretation`;
- `APPLIES_DEFINITION_FROM`: `applies definition from`,
  `source of applied definitions`, `applied definitions`;
- `REQUIRES_COMPLIANCE_WITH`: `requires compliance with`,
  `ensure full compliance`, `compliance with`, `direct readers to consult`.

The normative stop list is: `a`, `an`, `and`, `are`, `as`, `at`, `be`, `both`,
`by`, `does`, `for`, `from`, `how`, `in`, `is`, `it`, `of`, `on`, `or`, `that`,
`the`, `their`, `then`, `this`, `through`, `to`, `was`, `what`, `when`, `which`,
`who`, `with`.

Phrase matching is token-bounded, longest-first, and non-overlapping. Let `C(q)`
be relation types with a matched alias and `R(c)` the candidate relation-type
set. If `C(q)` is empty, relation coverage and precision are zero. Otherwise:

- `Coverage = |C(q) intersect R(c)| / |C(q)|`;
- `Precision = number of candidate triples whose type is in C(q) / m`;
- `ForwardAll = canonical-source-to-target traversals / all traversed triples`,
  maximized over retained matched-anchor traversals;
- `Orientation = 2*ForwardAll - 1`.

`Orientation` is deliberately described as **anchor-relative canonical
orientation**, not proof that the question's full natural-language semantics
have been resolved. It measures whether a candidate can be expanded from an
explicitly mentioned anchor mainly along, rather than against, declared edge
directions. It is independent of relation-alias matching.

### M0: matched relation-blind ranking

`M0(q,c) = Core(q,c)`.

M0 uses exactly the same candidates, normalization, node text, provenance,
length term, and tie-breaking as R1. Only relation-cue and direction terms are
removed.

### R1: relation-aware ranking

`R1(q,c) = Core(q,c) + 2.00*Coverage + 0.50*Precision + 0.50*Orientation`.

Ties are resolved by edge count then signature. `method_lock.json` is a
machine-readable copy of the lexicon, stop list, constants, allowlists, caps,
hashes, and Git commit.

### Prespecified ablations

- **Cue-off:** `Core + 0.50*Orientation`; no relation aliases are consulted.
- **Direction-off:** `Core + 2.00*Coverage + 0.50*Precision`.
- **M0:** `Core`, with both relation components removed.

All use the identical candidate set. R1 versus direction-off isolates the
anchor-relative orientation term, while R1 versus cue-off isolates lexical
relation-cue coverage and precision. B0 is a traversal reference, not a matched
causal comparison.

## Metrics and uncertainty

Each question has exactly one accepted canonical triple-set chain. Primary
metrics are exact-chain Hit@1, Hit@3, Hit@5, and MRR. For `N` ranked candidates,
Hit@k is one when Gold is present among the first `min(k,N)` candidates and zero
otherwise. Reciprocal rank is `1/rank`, or zero when absent. Candidate-generation
recall is the fraction of all 30 questions whose Gold signature occurs anywhere
in the retained candidates. Metrics are unweighted query macros overall and
within each fixed 10-question category.

Paired differences compare R1 with B0, M0, cue-off, and direction-off. The
paired bootstrap resamples questions within category: 10 draws with replacement
per category, concatenated to 30; 10,000 replicates; NumPy `PCG64` seed
`20260718`; percentile 95% intervals at 2.5% and 97.5%. No p-values or
superiority claim are made. The report discloses that questions were designed
from known graph relations and do not estimate arbitrary unseen graph questions.

## Failure handling and leakage controls

- Candidate generation and rankers read only sanitized queries, graph, and lock.
- Evaluation receives Gold only after rankings are serialized.
- Method-lock and inference files are separate and hashed.
- Missing provenance, duplicate IDs, malformed edges, anchor failures, cap/time
  truncation, and ambiguous aliases fail loudly or become explicit records.
- Original reviews, consensus workbook, and canonical graph are never modified.
- A validation step checks whether each final question uniquely identifies its
  accepted answer within the frozen graph; ambiguous items are reported and are
  not silently edited.

## Deliverables

- sanitized final Gold ledger and integrity manifest;
- `method_lock.json` written before score inspection;
- B0, M0, cue-off, direction-off, and R1 rankings;
- aggregate, category, bootstrap, sensitivity, and failure-analysis reports;
- tests for finalization, anchor detection, chain enumeration, duplicate-edge
  aggregation, direction scoring, ambiguity checks, and metrics;
- a concise manuscript update labelled supplementary and exploratory.
