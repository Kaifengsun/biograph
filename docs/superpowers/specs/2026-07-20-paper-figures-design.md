# Paper Figures Design Specification

## Scope

The manuscript uses exactly two full-width figures. Figure 1 explains the dual-path auditable evidence framework. Figure 2 summarizes the main confirmed experimental findings. Both figures use the same restrained journal style: white background, dark neutral strokes, pale lavender for regulatory text evidence, and pale green for structured graph evidence. Meaning must remain recoverable in grayscale through labels, ordering, and outlines rather than color alone.

## Figure 1: Dual-Path Framework

**Purpose.** Explain how analyst requests obtain citable regulatory text, provenance-backed structured relations, or both without treating generated content as evidence.

**Text path.** Frozen regulatory corpus -> document hierarchy -> BM25 over source chunks with separately evaluated optional neural reranking -> citable verbatim passage or table with hierarchy context as needed.

**Graph path.** Frozen openFDA shortage snapshot -> typed evidence graph -> bounded candidate generation and relation-cue ranking -> provenance-backed typed relation chain.

**Boundary conditions.** The task specifies text, graph, or both. Source-grounded summaries and synthetic questions are generated from the document hierarchy and guide text retrieval only. Text and graph evidence may be displayed separately or together but are evaluated separately.

**Caption.** `Overview of the proposed dual-path auditable evidence retrieval framework. Analyst requests may invoke text retrieval, structured relation-chain retrieval, or both. Generated summaries and synthetic questions guide retrieval but never replace citable source passages, tables, or provenance-bearing graph records.`

**Placement.** At the end of Task Definition, immediately before Methods.

## Figure 2: Findings at a Glance

**Purpose.** Present the three conclusions that support the manuscript's bounded architecture: BM25 is a strong text default; relation cues drive graph-chain ranking; and API-supply chains remain the main observed weakness.

### Panel (a): Text retrieval over source chunks

58 adjudicated questions, Hit@5:

| Method | Hit@5 | Hits |
|---|---:|---:|
| Qwen3 reranking over BM25* | 0.983 | 57/58 |
| BM25 | 0.948 | 55/58 |
| Selective gate | 0.897 | 52/58 |
| Youtu dense | 0.759 | 44/58 |
| MedCPT reranking over BM25* | 0.603 | 35/58 |
| MedCPT dense retrieval* | 0.345 | 20/58 |

The darker lavender fill identifies the primary BM25 baseline. It is visual emphasis, not a distinct task or evidence class.

### Panel (b): Evidence-chain ablation

Strict 28-question audit set, exact-chain Hit@5:

| Method | Hit@5 | Hits |
|---|---:|---:|
| Relation-aware | 0.786 | 22/28 |
| Direction off | 0.750 | 21/28 |
| Untyped traversal | 0.179 | 5/28 |
| Relation-blind | 0.143 | 4/28 |
| Relation cues off | 0.143 | 4/28 |

Green marks conditions that retain relation cues; gray marks controls that remove the key relation-aware structure.

### Panel (c): Relation-aware chain retrieval by task

Same strict 28-question audit set, exact-chain Hit@5:

| Slice | Hit@5 | Hits |
|---|---:|---:|
| Overall | 0.786 | 22/28 |
| Shortage chains | 1.000 | 10/10 |
| Regulatory logic | 0.900 | 9/10 |
| API supply | 0.375 | 3/8 |

All task slices use the same complete relation-aware method and therefore use the same green encoding. Low API-supply performance is conveyed by bar length, value, and annotation rather than a conflicting gray fill.

**Caption.** `Summary of source-chunk and evidence-chain retrieval results. (a) Hit@5 on 58 adjudicated text questions. Asterisks mark feedback-motivated post hoc extensions evaluated under subsequently locked, unchanged inference protocols after the Gold set had been observed; they are interpreted as boundary analyses. The 95% paired-bootstrap interval for the Qwen3-BM25 Hit@5 difference included zero. The darker lavender fill identifies the primary BM25 baseline. (b) Exact-chain Hit@5 for the relation-aware method and its controls on the strict 28-question audit set. (c) Exact-chain Hit@5 for the complete relation-aware method by task. Two questions with non-unique frozen-graph paths were retained in the 30-question audit record but excluded from strict exact-chain evaluation. Values show proportions and exact hit counts.`

**Placement.** After the graph-chain results at the end of Results.

## Source and Export Requirements

- Keep editable SVG sources and publication PNG exports together under `paper/figures/`.
- Export PNGs at 2,200 pixels wide, giving more than 300 dpi at the manuscript's full text width.
- Do not place a manuscript figure number or caption inside either image.
- Use LaTeX `figure` environments with `\linewidth`, stable labels, and `\Cref` references.
- Recompile and visually inspect the rendered PDF at page scale and enlarged scale.
