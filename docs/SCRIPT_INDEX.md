# Script Index

This index identifies the maintained entry points behind the paper. Historical
diagnostic scripts remain in place when they are referenced by frozen records,
but they are not all required for routine verification.

## Document corpus

| Task | Entry point |
| --- | --- |
| Run the document pipeline | `pharma_doc_pipeline/main.py` |
| Convert PDF to Markdown | `pharma_doc_pipeline/step_01_convert.py` |
| Build hierarchical chunks and tables | `pharma_doc_pipeline/step_02_chunk.py` |
| Generate source-grounded enrichment | `pharma_doc_pipeline/step_03_enrich.py` |
| Build vector indexes | `pharma_doc_pipeline/step_04_vectorize.py` |
| Attach hierarchy summaries | `attach_hierarchy_summaries_to_graph.py` |

## Structured evidence graph

| Task | Entry point |
| --- | --- |
| Collect openFDA shortage records | `collect_openfda_drug_shortages.py` |
| Normalize the frozen snapshot | `normalize_openfda_drug_shortages.py` |
| Build regulatory evidence graph | `build_regulatory_evidence_graph.py` |
| Add document relations | `extract_regulatory_document_relations.py` |
| Import graph data | `import_neo4j_data.py` |

## Retrieval and evaluation

| Task | Entry point |
| --- | --- |
| Three-path retrieval | `three_path_retrieval.py` |
| Freeze three-path evaluation set | `freeze_three_path_evaluation_set.py` |
| Evaluate three-path retrieval | `evaluate_three_path_retrieval.py` |
| BM25 and enrichment ablation | `evaluate_bm25_enrichment_ablation.py` |
| Adaptive text-first retrieval | `adaptive_text_first.py` |
| Selective reranking confirmation | `analyze_selective_confirmatory_results.py` |
| Double-annotation analysis | `tools/dual_annotation_60/analyze_dual_annotations.py` |
| Qwen3 locked extension | `tools/modern_reranker_58/run_locked_reranker.py` |
| MedCPT locked extension | `tools/medcpt_58/run_locked.py` |
| Relation-chain evaluation | `tools/relation_chain_ranking/evaluate.py` |

## Paper and audits

| Task | Entry point |
| --- | --- |
| Validate manuscript results | `paper/scripts/validate_paper.py` |
| Build the Word manuscript | `paper/scripts/build_word_manuscript.py` |
| Audit cleanup preservation | `tools/repository_cleanup_audit.py` |

## Recommended order

For routine checks, run the automated tests first and then manuscript
validation. Re-run data collection, LLM enrichment, model inference, or manual
annotation only when intentionally creating a new frozen experiment version.
