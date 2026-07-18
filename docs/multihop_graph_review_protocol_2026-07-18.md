# Multi-hop Graph Evidence Review Protocol

## Scope

The extension contains 30 graph-grounded questions drawn before path-ranking evaluation:

- 10 FDA shortage chains: event, reporting company, NDC product, and active ingredient.
- 10 API supply chains: drug, API, suppliers, and supplier country properties.
- 10 regulatory logic chains: principles, complements, definitions, interpretation, compliance, topic, or supersession relations.

## Independent review

Reviewer A and Reviewer B receive separate workbooks with identical questions and graph evidence. They must not compare labels before submission. For each question, the reviewer reads every displayed node, property, edge, and provenance source, then assigns:

- `Confirmed`: the complete question and chain are supported.
- `Revise`: the chain is useful but the question or relation wording must be narrowed.
- `Exclude`: the chain is unsupported, misleading, or lacks adequate provenance.

The workbook also records the reviewer's answer, complete-chain support, provenance adequacy, and rationale. Original labels will be retained. Disagreements will be jointly adjudicated before any accepted path becomes Gold.

## Evaluation boundary

No path-ranking score will be treated as formal until the two independent reviews and adjudication are complete. Accepted paths will support a relation-aware path-ranking comparison; rejected paths remain in the audit ledger. Graph nodes do not enter source-passage retrieval metrics.

Registry SHA-256: `f6639a42c99561782fd2d942df2271a2a3fbd43ac198a513d9edebb2baaa4e8a`.
