# Regulatory Relations and FDA Shortage Snapshot (2026-07-10)

## Scope

This report records a non-destructive extension of the staged regulatory
evidence graph. It preserves the frozen 32-document regulatory corpus, its
2,478 source chunks, its hierarchy summaries, all prior graph artifacts, and
the legacy Neo4j database. No existing corpus, vector index, or database was
replaced.

## Regulatory Relation Layer

Source: raw MinerU Markdown under `data/markdown`, restricted to documents
that also occur in the frozen corpus. The extractor is rule-based; a relation
is emitted only when its literal source pattern is found. Each edge records
the matching text, character offsets, source path, source SHA-256, and rule ID.

| Relation | Count | Meaning |
| --- | ---: | --- |
| `COVERS_TOPIC` | 12 | A scope/objective statement links a document to a regulatory topic. |
| `SUPERSEDES` | 7 | A document explicitly supersedes or consolidates another guideline/reference. |
| `COMPLEMENTS` | 5 | A document explicitly states that it complements another guideline. |
| `USES_PRINCIPLES_FROM` | 7 | A document explicitly adopts another guideline's principles, concepts, or approach. |
| `APPLIES_DEFINITION_FROM` | 1 | A document explicitly makes another guideline's definition applicable. |
| `INTERPRETS` | 2 | A document explicitly interprets an external legal instrument. |
| `REQUIRES_COMPLIANCE_WITH` | 1 | A document explicitly directs compliance with an external regulation. |

All 35 configured rules were accepted with source evidence. This layer does
not create generic `DEPENDS_ON` edges, because a citation alone does not prove
operational dependence. It also does not create document-to-document
`COVERS` edges; scope is represented as `COVERS_TOPIC` instead.

## FDA Drug-Shortage Snapshot

Source: public `openFDA` Drug Shortages endpoint,
`https://api.fda.gov/drug/shortages.json`. The raw snapshot is stored at
`artifacts/fda_openfda_drug_shortages/2026-07-10-openfda-drug-shortages-v2/`.

- Collection timestamp: `2026-07-10T14:18:43+00:00`.
- API/downloaded records: 1,637 across 17 hashed raw JSON pages.
- Initial posting-date range: 2012-01-01 to 2026-07-07.
- Current API status composition: 1,152 `Current`, 460 `To Be Discontinued`,
  and 25 `Resolved` records.
- 436 records include an FDA-provided `shortage_reason` field.
- Normalized graph artifacts: 3,582 nodes and 5,304 edges.

The FDA layer uses `FDA_DrugShortageEvent`, `FDANDCProduct`,
`FDAManufacturer`, and `FDAActiveIngredient` nodes. Its factual edges are
`AFFECTS_NDC_PRODUCT`, `REPORTED_BY`, and `HAS_ACTIVE_INGREDIENT`. Only 51
`SAME_AS_CANDIDATE` edges were added, each based on an exact normalized active
ingredient name and marked as a candidate rather than an asserted identity.

Existing `RecallEvent` nodes remain separate. The graph does not infer that a
recall, a cGMP event, an API dependency, or a regulatory clause caused a
shortage.

## Combined Snapshot

- Output: `artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda/`.
- Nodes: 7,578.
- Edges: 15,237.
- The extension manifest records SHA-256 hashes for the base snapshot and all
  appended artifacts.

During integrity validation, 18 `BELONGS_TO_AREA` edges inherited from the
base snapshot had source IDs absent from the node set. These are known
therapeutic drug-class identifiers from `DRUG_AREA_MAP`, not unsupported
facts. The new snapshot materializes them as `DrugClass` nodes with explicit
`pharma_supply_chain/core_data.py` provenance; no edge was removed.

## Experimental Use and Limits

The combined graph is ready for evidence-grounded retrieval and constrained
path discovery. A valid path may now connect a product or ingredient shortage
signal to a company, structured supply-chain context, an applicable regulatory
topic, and source chunks that carry the legal or technical evidence.

The FDA endpoint is a current mutable database. Its snapshot is appropriate
for retrieval, coverage analysis, and dated retrospective description. It is
not by itself a leakage-free time-series prediction dataset: future backtests
must restrict all features to their cut-off date and use archived historical
source snapshots or clearly report residual temporal-leakage risk.

## Verification

`python -m unittest discover -s tests -p 'test_*.py' -v` completed on
2026-07-10 with 37 passing tests. The suite includes the new relation-extractor
evidence checks, raw FDA-page hash/normalization checks, recall-versus-shortage
type separation checks, and graph-extension endpoint-integrity checks.

Official source documentation: [openFDA Drug Shortages](https://open.fda.gov/apis/drug/drugshortages/) and [searchable fields](https://open.fda.gov/apis/drug/drugshortages/searchable-fields/).
