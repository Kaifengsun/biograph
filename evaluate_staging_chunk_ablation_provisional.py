"""Run a provisional chunk-level R1-R4 screening on semantic candidate labels.

The labels come from a prior segmentation and automatic semantic alignment.
This script intentionally marks the output as non-formal until the evidence
chunks are reviewed against the frozen source corpus.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient


DEFAULT_QUERIES = Path("data/eval/eval_queries_deepseek_v4_semantic_candidate_2026-07-10.json")
DEFAULT_INDEX_ROOT = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")
DEFAULT_OUTPUT = DEFAULT_INDEX_ROOT / "provisional_chunk_level_ablation_eval.json"
VARIANTS = ("R1_raw", "R2_summary", "R3_hyde", "R4_table")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dedupe_records(metadata: list[dict[str, Any]], positions: list[int]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for position in positions:
        if position < 0 or position >= len(metadata):
            continue
        record = metadata[position]
        chunk_id = record.get("chunk_id", "")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        records.append(record)
    return records


def chunk_hit(records: list[dict[str, Any]], relevant: set[str], k: int) -> float:
    return float(bool({r.get("chunk_id") for r in records[:k]} & relevant))


def chunk_recall(records: list[dict[str, Any]], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    found = {r.get("chunk_id") for r in records[:k]} & relevant
    return len(found) / len(relevant)


def chunk_mrr(records: list[dict[str, Any]], relevant: set[str]) -> float:
    for rank, record in enumerate(records, 1):
        if record.get("chunk_id") in relevant:
            return 1.0 / rank
    return 0.0


def aggregate(rows: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
    result: dict[str, Any] = {"n_queries": len(rows)}
    for k in k_values:
        result[f"ChunkHit@{k}"] = round(
            sum(row[f"ChunkHit@{k}"] for row in rows) / len(rows), 4
        )
        result[f"ChunkRecall@{k}"] = round(
            sum(row[f"ChunkRecall@{k}"] for row in rows) / len(rows), 4
        )
    result["ChunkMRR"] = round(sum(row["ChunkMRR"] for row in rows) / len(rows), 4)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row.get("category", "unknown")].append(row)
    result["by_category"] = {
        category: {
            "n": len(group),
            "ChunkHit@5": round(sum(r["ChunkHit@5"] for r in group) / len(group), 4),
            "ChunkRecall@5": round(sum(r["ChunkRecall@5"] for r in group) / len(group), 4),
            "ChunkMRR": round(sum(r["ChunkMRR"] for r in group) / len(group), 4),
        }
        for category, group in sorted(by_category.items())
    }
    return result


def evaluate_variant(
    name: str,
    index_dir: Path,
    query_embeddings: np.ndarray,
    queries: list[dict[str, Any]],
    k_values: list[int],
) -> dict[str, Any]:
    index = faiss.read_index(str(index_dir / "pharma_docs.faiss"))
    metadata = read_json(index_dir / "pharma_docs.meta.json")
    max_k = max(k_values)
    search_k = min(index.ntotal, max(max_k * 8, max_k))
    _scores, positions = index.search(
        np.array(query_embeddings, dtype=np.float32, copy=True), search_k
    )
    rows: list[dict[str, Any]] = []
    for query, query_positions in zip(queries, positions):
        records = dedupe_records(metadata, list(query_positions))[:max_k]
        relevant = set(query.get("semantic_candidate_relevant_chunk_ids", []))
        row: dict[str, Any] = {
            "query_id": query.get("query_id"),
            "query": query.get("query"),
            "category": query.get("category"),
            "difficulty": query.get("difficulty"),
            "candidate_relevant_chunk_ids": sorted(relevant),
            "retrieved_top10": [
                {
                    "chunk_id": record.get("chunk_id"),
                    "doc_id": record.get("doc_id"),
                    "type": record.get("type"),
                    "heading": record.get("heading"),
                }
                for record in records[:10]
            ],
        }
        for k in k_values:
            row[f"ChunkHit@{k}"] = chunk_hit(records, relevant, k)
            row[f"ChunkRecall@{k}"] = chunk_recall(records, relevant, k)
        row["ChunkMRR"] = chunk_mrr(records, relevant)
        rows.append(row)
    return {
        "variant": name,
        "index_dir": str(index_dir),
        "vector_count": index.ntotal,
        "aggregate": aggregate(rows, k_values),
        "per_query": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run provisional chunk-level ablation screening")
    parser.add_argument("--queries", default=str(DEFAULT_QUERIES))
    parser.add_argument("--index-root", default=str(DEFAULT_INDEX_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--k", nargs="+", type=int, default=[1, 5, 10, 20])
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing result: {output}")
    queries = [
        row for row in read_json(Path(args.queries))
        if row.get("semantic_candidate_relevant_chunk_ids")
    ]
    if not queries:
        raise RuntimeError("no semantic candidate labels found")

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

    root = Path(args.index_root)
    variants = {
        name: evaluate_variant(name, root / name, query_embeddings, queries, args.k)
        for name in VARIANTS
    }
    payload = {
        "evaluation_type": "provisional_chunk_level_retrieval_screening",
        "query_count": len(queries),
        "query_source": str(args.queries),
        "index_root": str(root),
        "embedding_model": settings.embedding.local_model,
        "k_values": args.k,
        "elapsed_seconds": round(time.time() - started, 2),
        "formal_chunk_level_metrics_ready": False,
        "label_status": "semantic_candidate_mappings_need_source_review",
        "limitation": (
            "Chunk labels were aligned from a prior segmentation and are not frozen ground truth. "
            "Use this output for engineering diagnosis only; do not report it as the paper's final metric."
        ),
        "variants": variants,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: result["aggregate"] for name, result in variants.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
