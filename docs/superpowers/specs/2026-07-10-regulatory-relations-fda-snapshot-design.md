# Regulatory Relations and FDA Shortage Snapshot Design

## Purpose

Extend the staged pharmaceutical evidence graph with provenance-preserving
regulatory-document relations and a dated FDA drug-shortage snapshot. The
extension supports evidence retrieval and retrospective risk-path discovery;
it does not claim to predict shortage duration or establish causality.

## Source Boundaries

- Regulatory relation evidence is read from `data/markdown/<doc_id>/<doc_id>.md`
  only when `<doc_id>` is present in the frozen 32-document corpus.
- The frozen enriched corpus at
  `data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4` remains unchanged.
- The legacy `data/chunks`, legacy FAISS indexes, and existing Neo4j database
  are excluded from all inputs.
- FDA shortage records are downloaded from `https://api.fda.gov/drug/shortages.json`.
  Raw API pages and the normalized snapshot are immutable new artifacts.

## Regulatory Relation Model

The graph stores fine-grained relations rather than a generic document-to-
document `COVERS` or `DEPENDS_ON` relation.

| Relation | Source node | Target node | Admission rule |
|---|---|---|---|
| `COVERS_TOPIC` | RegulatoryDocument | RegulatoryTopic | A scope, objective, or explicit applicability statement names the topic. |
| `SUPERSEDES` | RegulatoryDocument | RegulatoryDocument or ExternalRegulatoryReference | The text explicitly says it supersedes or consolidates the target. |
| `COMPLEMENTS` | RegulatoryDocument | RegulatoryDocument | The text explicitly says it complements the target. |
| `USES_PRINCIPLES_FROM` | RegulatoryDocument | RegulatoryDocument | The text explicitly says principles, concepts, or approaches from the target are used or applicable. |
| `APPLIES_DEFINITION_FROM` | RegulatoryDocument | RegulatoryDocument | The text explicitly identifies a definition from the target as applicable. |
| `INTERPRETS` | RegulatoryDocument | ExternalRegulatoryReference | The text explicitly describes interpretation of an external legal or regulatory source. |
| `REQUIRES_COMPLIANCE_WITH` | RegulatoryDocument | ExternalRegulatoryReference | The text explicitly directs readers to comply with the referenced regulation. |

Every edge records `source_doc_id`, a quoted source span, source locator,
relation rule identifier, source file SHA-256, and `derivation=explicit_text`.
Ambiguous references, topical similarity, a table-of-contents mention, and
ordinary bibliography entries do not create any of these relations.

## FDA Shortage Snapshot Model

The collector fetches all paginated records from the public openFDA endpoint
with a fixed 100-record page size and retry/backoff. It writes the unmodified
API pages and a normalized JSONL view under a date-stamped snapshot directory.

`FDA_DrugShortageEvent` nodes retain the FDA product and event fields,
including NDC, generic/proprietary name, company, status, shortage reason,
initial posting date, change date, update date, and discontinuation date.
The graph adds only direct factual relations:

- `AFFECTS_NDC_PRODUCT` from a shortage event to an FDA NDC-product node.
- `REPORTED_BY` from a shortage event to the FDA-reported company node.
- `HAS_ACTIVE_INGREDIENT` from an NDC-product node to a normalized FDA
  ingredient node when `openfda.substance_name` is supplied.
- `SAME_AS_CANDIDATE` from an FDA ingredient/product to an existing structured
  drug only when an exact normalized name, RxCUI, UNII, NDC, or application
  identifier supports it. Candidate edges never assert causal supply-chain
  equivalence and retain the matching identifier.

The existing `RecallEvent` records remain separate. A recall, a cGMP issue,
and a shortage are distinct event types. No relation from recall to shortage
is inferred from co-occurrence.

## Temporal Interpretation

The endpoint is a current, mutable representation of FDA source data. The
snapshot is therefore suitable for graph coverage, evidence retrieval, and
dated retrospective descriptions. A future time-sliced prediction experiment
must restrict all visible fields to the cut-off date and use independently
archived historical snapshots or explicitly document residual temporal-leakage
risk. It must not use current status or later updates as features for an
earlier cut-off.

## Validation

- Source files must map one-to-one to frozen document IDs before relation
  extraction begins.
- Every document relation must point to an existing node or a deterministic
  external-reference node and include an exact evidence span.
- A relation extractor test suite must reject bibliography-only and ambiguous
  citations.
- The FDA collector must preserve API pagination metadata, page hashes,
  collection timestamp, record count, and source URL.
- Normalized FDA IDs must be deterministic across reruns over the same raw
  pages.
- Every FDA graph edge must resolve to an existing node and retain snapshot
  provenance.
