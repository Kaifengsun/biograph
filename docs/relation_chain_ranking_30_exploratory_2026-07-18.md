# Exploratory Relation-Aware Evidence-Chain Ranking

## Status and scope

This feedback-driven supplementary experiment evaluates exact evidence-chain ranking inside a declared pharmaceutical supply and regulatory graph view. It is exploratory because the 30 questions were constructed from known graph relations. It does not estimate performance on arbitrary unseen graph questions and does not establish causal inference or general multi-hop reasoning.

The frozen pool contains 10 shortage-chain, 10 API-supply-chain, and 10 regulatory-logic questions. Candidate chains contain one to five canonical directed triples and may branch. All methods rank the same candidates generated from a fixed 12-relation projection without reading Gold fields.

## Audit qualification

Independent review and joint adjudication resolved every item. A final full-graph ambiguity audit identified two API questions, `MH-SC04` and `MH-SC08`, whose wording admitted both a finished-product API form and an upstream intermediate branch. They remain in the 30-question audit ledger and unfiltered result but are excluded from the strict complete-chain metrics. The strict set therefore contains 28 questions: 10 shortage, 8 API supply, and 10 regulatory logic.

Candidate generation recovered the accepted chain for every question. Twelve queries reached the deterministic 50,000-candidate cap; none hit the work-unit abort limit and none lacked an eligible anchor.

## Compared conditions

- **B0** ranks by edge count and canonical signature only.
- **M0** adds question--node token overlap, provenance coverage, and a chain-length penalty.
- **Cue-off** retains M0 and anchor-relative orientation but removes relation-phrase matching.
- **Direction-off** retains relation coverage and precision but removes orientation.
- **R1** combines M0, relation coverage, relation precision, and orientation.

Weights, aliases, stop words, limits, graph hashes, and tie-breaking are recorded in the method lock. The strict audit decision is an evaluation layer over unchanged v4 rankings.

## Strict 28-question result

| Method | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|
| B0 | 0.000 | 0.036 | 0.179 | 0.067 |
| M0 | 0.036 | 0.107 | 0.143 | 0.140 |
| Cue-off | 0.036 | 0.071 | 0.143 | 0.180 |
| Direction-off | 0.500 | 0.714 | 0.750 | 0.600 |
| R1 | 0.571 | 0.786 | 0.786 | 0.663 |

R1 minus M0 was +0.643 for Hit@5, with a 10,000-sample category-stratified bootstrap interval of [0.464, 0.821]. R1 minus direction-off was +0.036 [-0.071, 0.143]. The observed improvement therefore came mainly from explicit relation-cue coverage and precision; the incremental orientation contribution was small and uncertain.

## R1 category slices

| Category | n | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|---:|
| Shortage chain | 10 | 1.000 | 1.000 | 1.000 | 1.000 |
| Regulatory logic | 10 | 0.600 | 0.900 | 0.900 | 0.701 |
| API supply chain | 8 | 0.000 | 0.375 | 0.375 | 0.195 |

The large slice difference is substantive: shortage questions closely match explicit record relations, whereas API supply chains branch across finished forms, intermediates, and multiple suppliers.

## Transparent unfiltered result

| Method | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|
| B0 | 0.000 | 0.033 | 0.167 | 0.064 |
| M0 | 0.033 | 0.100 | 0.133 | 0.135 |
| Cue-off | 0.033 | 0.067 | 0.133 | 0.173 |
| Direction-off | 0.467 | 0.667 | 0.700 | 0.566 |
| R1 | 0.533 | 0.733 | 0.733 | 0.626 |

## Reproducibility boundary

Public code is under `tools/relation_chain_ranking/`, with focused tests in `tests/test_relation_chain_ranking.py`. Private review workbooks, copyrighted source passages, local graph artifacts, and multi-gigabyte ranking manifests are excluded from Git. The local audit archive retains the frozen Gold ledger, inference-only questions, method lock, per-query rankings, reviewer decisions, hashes, and both strict and unfiltered evaluations.

An earlier v3 execution exposed an anchor-eligibility defect: isolated alias matches could consume the fixed anchor cap. Those outputs were preserved, the defect was covered by tests, and v4 regenerated rankings after restricting anchors to nodes incident to the fixed task projection. The human ambiguity decision was applied only after v4 ranking and did not alter candidates or scores.
