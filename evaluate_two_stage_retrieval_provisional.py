"""Diagnose HyDE-as-navigation followed by source-chunk evidence retrieval.

Stage 1 uses the R3 summary+HyDE index to select candidate documents. Stage 2
uses only the R2 source-chunk index and filters it to those documents. Labels
remain semantic candidates, so this output is provisional.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient


QUERIES = Path("data/eval/eval_queries_deepseek_v4_semantic_candidate_2026-07-10.json")
INDEX_ROOT = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")
OUTPUT = INDEX_ROOT / "two_stage_provisional_eval.json"
DOC_BUDGETS = (1, 3, 5)
K_VALUES = (1, 5, 10, 20)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        chunk_id = record.get("chunk_id", "")
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            result.append(record)
    return result


def metrics(records: list[dict[str, Any]], relevant: set[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for k in K_VALUES:
        found = {r.get("chunk_id") for r in records[:k]} & relevant
        result[f"ChunkHit@{k}"] = float(bool(found))
        result[f"ChunkRecall@{k}"] = len(found) / len(relevant) if relevant else 0.0
    result["ChunkMRR"] = next(
        (1.0 / rank for rank, row in enumerate(records, 1) if row.get("chunk_id") in relevant),
        0.0,
    )
    return result


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"refusing to overwrite existing result: {OUTPUT}")
    queries = [
        row for row in read_json(QUERIES)
        if row.get("semantic_candidate_relevant_chunk_ids")
    ]
    settings = PipelineSettings()
    settings.embedding = EmbeddingConfig(
        backend="local",
        local_model=settings.embedding.local_model,
        dimension=settings.embedding.dimension,
    )
    embedder = EmbeddingClient(settings.embedding)
    started = time.time()
    query_embeddings = embedder.embed([row["query"] for row in queries], batch_size=8)
    faiss.normalize_L2(query_embeddings)

    hyde_index = faiss.read_index(str(INDEX_ROOT / "R3_hyde/pharma_docs.faiss"))
    hyde_meta = read_json(INDEX_ROOT / "R3_hyde/pharma_docs.meta.json")
    source_index = faiss.read_index(str(INDEX_ROOT / "R2_summary/pharma_docs.faiss"))
    source_meta = read_json(INDEX_ROOT / "R2_summary/pharma_docs.meta.json")

    hyde_search_k = min(hyde_index.ntotal, 240)
    source_search_k = source_index.ntotal
    _hyde_scores, hyde_positions = hyde_index.search(
        np.array(query_embeddings, dtype=np.float32, copy=True), hyde_search_k
    )
    _source_scores, source_positions = source_index.search(
        np.array(query_embeddings, dtype=np.float32, copy=True), source_search_k
    )

    variants: dict[str, Any] = {}
    for budget in DOC_BUDGETS:
        rows: list[dict[str, Any]] = []
        for query, h_positions, s_positions in zip(queries, hyde_positions, source_positions):
            ranked_docs: list[str] = []
            for position in h_positions:
                if position < 0 or position >= len(hyde_meta):
                    continue
                doc_id = hyde_meta[position].get("doc_id", "")
                if doc_id and doc_id not in ranked_docs:
                    ranked_docs.append(doc_id)
            selected_docs = set(ranked_docs[:budget])
            source_records = [
                source_meta[position]
                for position in s_positions
                if 0 <= position < len(source_meta)
                and source_meta[position].get("doc_id") in selected_docs
            ]
            records = dedupe(source_records)
            relevant = set(query["semantic_candidate_relevant_chunk_ids"])
            row = {
                "query_id": query.get("query_id"),
                "query": query.get("query"),
                "category": query.get("category"),
                "selected_doc_ids": ranked_docs[:budget],
                "candidate_relevant_chunk_ids": sorted(relevant),
                "retrieved_top10": [
                    {
                        "chunk_id": r.get("chunk_id"),
                        "doc_id": r.get("doc_id"),
                        "heading": r.get("heading"),
                    }
                    for r in records[:10]
                ],
            }
            row.update(metrics(records, relevant))
            rows.append(row)
        aggregate = {"n_queries": len(rows)}
        for key in ("ChunkHit@1", "ChunkHit@5", "ChunkRecall@5", "ChunkMRR"):
            aggregate[key] = round(sum(row[key] for row in rows) / len(rows), 4)
        variants[f"HyDE_docs_{budget}_then_R2_source"] = {
            "document_budget": budget,
            "aggregate": aggregate,
            "per_query": rows,
        }

    payload = {
        "evaluation_type": "provisional_two_stage_retrieval_screening",
        "query_count": len(queries),
        "query_source": str(QUERIES),
        "index_root": str(INDEX_ROOT),
        "embedding_model": settings.embedding.local_model,
        "stage_1": "R3 summary + HyDE selects documents",
        "stage_2": "R2 summary source chunks filtered to selected documents",
        "formal_chunk_level_metrics_ready": False,
        "label_status": "semantic_candidate_mappings_need_source_review",
        "elapsed_seconds": round(time.time() - started, 2),
        "variants": variants,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: value["aggregate"] for name, value in variants.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
