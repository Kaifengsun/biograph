"""Evaluate R1-R4 staging indexes with stable document-level labels.

This evaluator deliberately reports document-level retrieval metrics only. The
legacy query set has stable relevant document labels but chunk labels from an
older segmentation, so chunk-level metrics remain blocked on human review of
the candidate evidence alignment artifacts.
"""

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import faiss
import numpy as np

from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient


DEFAULT_QUERIES = Path("data/eval_queries.json")
DEFAULT_INDEX_ROOT = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")
DEFAULT_OUTPUT = DEFAULT_INDEX_ROOT / "document_level_ablation_eval.json"
VARIANTS = ("R1_raw", "R2_summary", "R3_hyde", "R4_table")
DOC_ID_MAP = {
    "EMA GMP Annex 11": "ema_gmp_annex_11",
    "FDA CGMP Guidance": "fda_cgmp_guidance",
    "ICH M7 R2": "ich_m7_r2",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dedupe_chunk_records(metadata: List[Dict[str, Any]], positions: List[int]) -> List[Dict[str, Any]]:
    seen = set()
    records = []
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


def doc_hit(records: List[Dict[str, Any]], relevant_docs: set[str], k: int) -> float:
    return float(any(record.get("doc_id") in relevant_docs for record in records[:k]))


def doc_recall(records: List[Dict[str, Any]], relevant_docs: set[str], k: int) -> float:
    if not relevant_docs:
        return 0.0
    found = {record.get("doc_id") for record in records[:k]}
    return len(found & relevant_docs) / len(relevant_docs)


def doc_mrr(records: List[Dict[str, Any]], relevant_docs: set[str]) -> float:
    for rank, record in enumerate(records, 1):
        if record.get("doc_id") in relevant_docs:
            return 1.0 / rank
    return 0.0


def aggregate(per_query: List[Dict[str, Any]], k_values: List[int]) -> Dict[str, Any]:
    output: Dict[str, Any] = {"n_queries": len(per_query)}
    for k in k_values:
        output[f"DocHit@{k}"] = round(
            sum(row[f"DocHit@{k}"] for row in per_query) / len(per_query), 4
        )
        output[f"DocRecall@{k}"] = round(
            sum(row[f"DocRecall@{k}"] for row in per_query) / len(per_query), 4
        )
    output["DocMRR"] = round(sum(row["DocMRR"] for row in per_query) / len(per_query), 4)

    by_category = defaultdict(list)
    for row in per_query:
        by_category[row.get("category", "unknown")].append(row)
    output["by_category"] = {}
    for category, rows in sorted(by_category.items()):
        output["by_category"][category] = {
            "n": len(rows),
            "DocHit@5": round(sum(row["DocHit@5"] for row in rows) / len(rows), 4),
            "DocRecall@5": round(sum(row["DocRecall@5"] for row in rows) / len(rows), 4),
            "DocMRR": round(sum(row["DocMRR"] for row in rows) / len(rows), 4),
        }
    return output


def evaluate_variant(
    name: str,
    index_dir: Path,
    query_embeddings: np.ndarray,
    queries: List[Dict[str, Any]],
    k_values: List[int],
) -> Dict[str, Any]:
    index = faiss.read_index(str(index_dir / "pharma_docs.faiss"))
    metadata = read_json(index_dir / "pharma_docs.meta.json")
    max_k = max(k_values)
    search_k = min(index.ntotal, max(max_k * 8, max_k))
    scores, positions = index.search(np.array(query_embeddings, dtype=np.float32, copy=True), search_k)

    per_query = []
    for query, query_scores, query_positions in zip(queries, scores, positions):
        records = dedupe_chunk_records(metadata, list(query_positions))[:max_k]
        relevant_docs = {DOC_ID_MAP[name] for name in query.get("relevant_docs", []) if name in DOC_ID_MAP}
        row = {
            "query_id": query.get("query_id"),
            "query": query.get("query"),
            "category": query.get("category"),
            "difficulty": query.get("difficulty"),
            "relevant_doc_ids": sorted(relevant_docs),
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
            row[f"DocHit@{k}"] = doc_hit(records, relevant_docs, k)
            row[f"DocRecall@{k}"] = doc_recall(records, relevant_docs, k)
        row["DocMRR"] = doc_mrr(records, relevant_docs)
        per_query.append(row)

    return {
        "variant": name,
        "index_dir": str(index_dir),
        "vector_count": index.ntotal,
        "aggregate": aggregate(per_query, k_values),
        "per_query": per_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate staging retrieval ablations")
    parser.add_argument("--queries", default=str(DEFAULT_QUERIES))
    parser.add_argument("--index-root", default=str(DEFAULT_INDEX_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--k", nargs="+", type=int, default=[1, 5, 10, 20])
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing result: {output}")
    raw_queries = read_json(Path(args.queries))
    queries = [
        row for row in raw_queries
        if row.get("status") == "annotated"
        and all(name in DOC_ID_MAP for name in row.get("relevant_docs", []))
    ]
    if not queries:
        raise RuntimeError("no compatible annotated queries found")

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
    results = {}
    for variant in VARIANTS:
        index_dir = root / variant
        if not (index_dir / "pharma_docs.faiss").exists():
            raise FileNotFoundError(index_dir / "pharma_docs.faiss")
        results[variant] = evaluate_variant(
            variant, index_dir, query_embeddings, queries, args.k
        )

    payload = {
        "evaluation_type": "document_level_retrieval_screening",
        "query_count": len(queries),
        "query_source": str(args.queries),
        "index_root": str(root),
        "embedding_model": settings.embedding.local_model,
        "k_values": args.k,
        "elapsed_seconds": round(time.time() - started, 2),
        "formal_chunk_level_metrics_ready": False,
        "limitation": (
            "Legacy chunk-level evidence labels use a prior segmentation. These results "
            "use stable relevant-document labels only and are not a substitute for manually "
            "validated chunk-level Recall/MRR."
        ),
        "variants": results,
    }
    write_json(output, payload)
    summary = {
        name: result["aggregate"]
        for name, result in results.items()
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
