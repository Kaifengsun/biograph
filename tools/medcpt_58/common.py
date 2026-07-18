"""Shared deterministic helpers for the feedback-motivated MedCPT extension."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from develop_source_chunk_reranker import load_corpus
from tools.modern_reranker_58.common import (
    aggregate,
    corpus_manifest,
    metric_row,
    paired_bootstrap,
    read_json,
    sha256_file,
    sha256_json,
    write_json,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "data/eval/dual_annotation_58_formal_run_ready_2026-07-16.json"
DEFAULT_CORPUS = ROOT / "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4"
DEFAULT_BM25_CANDIDATES = (
    ROOT / "outputs/modern_reranker_58_2026-07-16/"
    "frozen_bm25_top50_candidates_qwen3_direct_v1.json"
)
QUERY_MODEL_ID = "ncbi/MedCPT-Query-Encoder"
QUERY_REVISION = "d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc"
ARTICLE_MODEL_ID = "ncbi/MedCPT-Article-Encoder"
ARTICLE_REVISION = "d05a736da4bb84ee4057b7f7999485be6ed85465"
CROSS_MODEL_ID = "ncbi/MedCPT-Cross-Encoder"
CROSS_REVISION = "71caf65d4927987813984f54c284405a13fcca49"
QUERY_MAX_LENGTH = 64
ARTICLE_MAX_LENGTH = 512
CROSS_MAX_LENGTH = 512
CANDIDATE_DEPTH = 50
CORPUS_DEPTH = 2478
PRESENTATION_DEPTH = 5
BOOTSTRAP_ITERATIONS = 10_000
BOOTSTRAP_SEED = 20_260_718
METRICS = ("hit_at_1", "hit_at_3", "hit_at_5", "hit_at_50", "mrr_at_50", "ndcg_at_5")


def runtime_model_manifest(snapshot_path: Path) -> list[dict[str, Any]]:
    """Hash runtime files while ignoring downloader state and caches."""
    files = [
        path
        for path in sorted(snapshot_path.rglob("*"))
        if path.is_file() and ".cache" not in path.parts and path.suffix != ".aria2"
    ]
    return [
        {
            "name": path.relative_to(snapshot_path).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in files
    ]


def normalize(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def article_pair(record: dict[str, Any]) -> list[str]:
    """Represent each source chunk using MedCPT's title-and-abstract interface."""
    title_parts = [normalize(record.get("parents_context")), normalize(record.get("heading"))]
    title = " | ".join(part for part in title_parts if part)
    body = normalize(record.get("content"))
    return [title, body]


def cross_passage(record: dict[str, Any]) -> str:
    title, body = article_pair(record)
    return "\n".join(part for part in (title, body) if part)


def prepare_dense_corpus(corpus_path: Path) -> dict[str, Any]:
    corpus, _ = load_corpus(corpus_path)
    rows = [
        {
            "chunk_id": str(record["chunk_id"]),
            "article_pair": article_pair(record),
            "cross_passage": cross_passage(record),
        }
        for record in corpus
    ]
    if len(rows) != CORPUS_DEPTH or len({row["chunk_id"] for row in rows}) != CORPUS_DEPTH:
        raise ValueError("dense corpus must contain 2478 unique source chunks")
    return {
        "schema_version": "1.0",
        "status": "frozen_before_medcpt_scores",
        "source_record_count": len(rows),
        "unicode_normalization": "NFC",
        "article_payload_fields": ["parents_context + heading", "content"],
        "records": rows,
    }


def rank_scores(chunk_ids: list[str], scores: np.ndarray) -> list[dict[str, Any]]:
    if len(chunk_ids) != len(scores):
        raise ValueError("chunk IDs and scores have different lengths")
    order = sorted(range(len(chunk_ids)), key=lambda i: (-float(scores[i]), chunk_ids[i]))
    return [
        {"chunk_id": chunk_ids[index], "score": float(scores[index]), "rank": rank}
        for rank, index in enumerate(order, 1)
    ]


def evaluate_rankings(
    queries: list[dict[str, Any]],
    rankings: dict[str, dict[str, list[str]]],
    methods: Iterable[str],
) -> dict[str, Any]:
    methods = tuple(methods)
    per_query = []
    for row in queries:
        query_id = row["annotation_id"]
        gold = set(row["gold_evidence_chunk_ids"])
        per_query.append({
            "annotation_id": query_id,
            "query_slice": row["query_slice"],
            "metrics": {
                method: metric_row(rankings[query_id][method], gold) for method in methods
            },
            "rankings": {method: rankings[query_id][method] for method in methods},
        })
    aggregate_rows = {
        method: aggregate(row["metrics"][method] for row in per_query) for method in methods
    }
    slices = sorted({row["query_slice"] for row in per_query})
    by_slice = {
        query_slice: {
            method: aggregate(
                row["metrics"][method]
                for row in per_query
                if row["query_slice"] == query_slice
            )
            for method in methods
        }
        for query_slice in slices
    }
    return {"aggregate": aggregate_rows, "by_slice": by_slice, "per_query": per_query}
