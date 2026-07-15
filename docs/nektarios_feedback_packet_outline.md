# Nektarios Feedback Packet Outline

## Purpose

Prepare a concise 6 to 8 page feedback packet before polishing the full manuscript. The packet should help Nektarios Oraiopoulos evaluate the research question, contribution positioning, experiment credibility, and most suitable publication lane.

## Page 1: Research Question And Positioning

### Working Title

*Beyond Time Series: Enhancing Dynamic Capabilities in Pharmaceutical Supply Chain Risk Control via GraphRAG and Agentic Simulation*

### Research Question

How can a domain-specific GraphRAG system improve evidence-grounded sensing, seizing, and transforming decisions for pharmaceutical supply-chain risk management when relevant compliance signals are distributed across structured pharmaceutical data and unstructured regulatory documents?

### Conservative Claim

PharmGraphRAG is a decision-support framework for regulatory evidence retrieval, cross-document reasoning, and supply-chain disruption scenario analysis. Direct drug-shortage forecasting should be presented only if leakage-free experiments support it.

## Page 2: Contributions To Validate

1. A heterogeneous pharmaceutical knowledge graph connecting structured pharmaceutical entities, regulatory documents, document chunks, tables, and cross-document references.
2. A three-stage GraphRAG retriever combining dense retrieval, document-structure exploration, and LLM-guided graph walk.
3. A GraphRAG-supported agent simulation layer that maps evidence-grounded actions to sensing, seizing, and transforming capabilities.
4. An empirical evaluation that separates retrieval improvement, component contribution, historical calibration, and managerial scenario analysis.

## Page 3: System Diagram Checklist

The architecture diagram should include:

- Data sources: FDA, ChEMBL, RxNorm, ICH, EMA, FDA guidance.
- Pipeline: PDF conversion, chunking, enrichment, table extraction, QAPair generation, embeddings.
- Storage: Neo4j graph, FAISS index, Neo4j vector index if QAPair pilot succeeds.
- Retrieval: Stage 1 bottom-up, Stage 2 top-down, Stage 3 LLM-guided walk.
- Simulation: ManufacturerAgent, DistributorAgent, RegulatorAgent.
- Outputs: evidence-grounded risk report, historical calibration metrics, policy scenario comparison.

## Page 4: Retrieval Experiment Design

| Experiment | Methods | Required Output |
|---|---|---|
| Retrieval benchmark | BM25, Dense FAISS, Dense+HyDE, Stage 1, Stage 1+2, random walk, full PharmGraphRAG | Recall@5/10/20, MRR, NDCG@10, evidence precision, latency, LLM calls |
| Query-type analysis | Single clause, document structure, cross-document, supply-chain scenario | Per-category results and failure cases |
| Component ablation | Sibling expansion, top-down exploration, REFERENCES traversal, table summaries, QAPair | Incremental contribution table |
| Robustness | Random walk with at least 5 seeds | Mean and 95% bootstrap confidence interval |

## Page 5: Simulation Experiment Design

### Historical Calibration

Compare `llm_only`, `flat_rag`, and `pharm_graphrag` modes after removing historical-outcome leakage.

### Metrics

- Shortage Duration Error
- Peak severity error
- Trajectory RMSE
- Cumulative unmet demand
- Sensing-Seizing-Transforming timing MAE

### Managerial Scenario Matrix

| Policy | Low Shock | Medium Shock | High Shock |
|---|---|---|---|
| Single-source baseline | Run | Run | Run |
| Dual-sourcing | Run | Run | Run |
| Inventory buffer | Run | Run | Run |
| Regulatory fast-track | Run | Run | Run |

## Page 6: Preliminary Results Slots

Fill this page only after repaired experiments run.

| Claim | Result Artifact | Value |
|---|---|---|
| Full GraphRAG vs Dense FAISS Recall@5 | `data/eval/results_retrieval_v1.json` | Pending |
| Full GraphRAG vs random walk Recall@5 | `data/eval/results_retrieval_v1.json` | Pending |
| REFERENCES traversal contribution | `data/eval/results_references_ablation.json` | Pending |
| Table summary contribution | `data/eval/results_table_ablation.json` | Pending |
| QAPair pilot contribution | `data/eval/results_qapair_pilot.json` | Pending |
| Leakage-free simulation trajectory RMSE | `simulation_results/historical_calibration_v1.json` | Pending |
| Best policy under high shock | `simulation_results/scenario_matrix_v1.json` | Pending |

## Page 7: Questions For Advisor Feedback

1. Is the strongest publishable framing decision support for pharmaceutical supply-chain risk control, or should the paper emphasize healthcare analytics, operations resilience, or information systems?
2. Is the Dynamic Capabilities framing sufficiently integrated into the computational evaluation, or should it be treated as a managerial interpretation rather than a central theoretical contribution?
3. Given the repaired experiment design, should the first submission prioritize a focused Scopus supply-chain analytics journal or a broader intelligent-systems journal?

## Page 8: Venue Strategy

Use `docs/submission_target_matrix.md` as the source. Present:

- Recommended first target.
- Stretch target if results become stronger.
- Conference backup route for October 2026 application timing.
- Explicit reasons for avoiding low-quality fast-publication venues.

