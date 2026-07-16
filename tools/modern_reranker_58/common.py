"""Shared deterministic helpers for the supplementary BGE reranker analysis."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from develop_source_chunk_reranker import load_corpus
from source_chunk_reranker import BM25Index, source_text


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "data/eval/dual_annotation_58_formal_run_ready_2026-07-16.json"
DEFAULT_CORPUS = ROOT / "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4"
MODEL_ID = "BAAI/bge-reranker-v2-m3"
MODEL_MAX_LENGTH = 512
CANDIDATE_DEPTH = 50
PRESENTATION_DEPTH = 5
BOOTSTRAP_ITERATIONS = 10_000
BOOTSTRAP_SEED = 20_260_716


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def frozen_corpus_files(corpus_path: Path) -> list[Path]:
    return sorted((*corpus_path.glob("*_enriched.json"), *corpus_path.glob("*_tables.json")))


def corpus_manifest(corpus_path: Path) -> list[dict[str, Any]]:
    return [
        {"name": path.name, "size": path.stat().st_size, "sha256": sha256_file(path)}
        for path in frozen_corpus_files(corpus_path)
    ]


def normalized_payload(record: dict[str, Any]) -> str:
    return unicodedata.normalize("NFC", source_text(record, max_chars=2000))


def prepare_bm25_candidates(pack_path: Path, corpus_path: Path) -> dict[str, Any]:
    pack = read_json(pack_path)
    queries = pack.get("queries", [])
    if len(queries) != 58:
        raise ValueError(f"expected 58 adjudicated queries, got {len(queries)}")
    corpus, _ = load_corpus(corpus_path)
    records = {str(row["chunk_id"]): row for row in corpus}
    bm25 = BM25Index.build(corpus)
    rows: list[dict[str, Any]] = []
    for query_row in queries:
        ranking = bm25.rank(str(query_row["query"]), CANDIDATE_DEPTH)
        if len(ranking) != CANDIDATE_DEPTH or len(set(ranking)) != CANDIDATE_DEPTH:
            raise ValueError(
                f"{query_row['annotation_id']} did not yield {CANDIDATE_DEPTH} unique BM25 candidates"
            )
        rows.append({
            "annotation_id": query_row["annotation_id"],
            "query_slice": query_row["query_slice"],
            "query": unicodedata.normalize("NFC", str(query_row["query"])),
            "gold_evidence_chunk_ids": list(query_row["gold_evidence_chunk_ids"]),
            "candidates": [
                {
                    "chunk_id": chunk_id,
                    "bm25_rank": rank,
                    "passage": normalized_payload(records[chunk_id]),
                }
                for rank, chunk_id in enumerate(ranking, 1)
            ],
        })
    return {
        "schema_version": "1.0",
        "status": "frozen_bm25_top50_candidates_before_neural_scores",
        "query_count": len(rows),
        "candidate_depth": CANDIDATE_DEPTH,
        "payload_fields": ["parents_context", "heading", "content"],
        "payload_max_chars": 2000,
        "unicode_normalization": "NFC",
        "queries": rows,
    }


def rank_scored_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any("score" not in row for row in candidates):
        raise ValueError("every candidate requires a score")
    ranked = sorted(
        candidates,
        key=lambda row: (-float(row["score"]), int(row["bm25_rank"]), str(row["chunk_id"])),
    )
    if len({row["chunk_id"] for row in ranked}) != len(ranked):
        raise ValueError("duplicate chunk IDs in scored candidates")
    return [dict(row, reranker_rank=index) for index, row in enumerate(ranked, 1)]


def metric_row(ranking: list[str], gold: set[str]) -> dict[str, float]:
    if not gold:
        raise ValueError("Gold set must not be empty")
    ranks = [index for index, chunk_id in enumerate(ranking[:CANDIDATE_DEPTH], 1) if chunk_id in gold]
    first = min(ranks) if ranks else None
    ideal_hits = min(len(gold), PRESENTATION_DEPTH)
    ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    dcg = sum(
        1.0 / math.log2(index + 1)
        for index, chunk_id in enumerate(ranking[:PRESENTATION_DEPTH], 1)
        if chunk_id in gold
    )
    return {
        "hit_at_1": float(first is not None and first <= 1),
        "hit_at_3": float(first is not None and first <= 3),
        "hit_at_5": float(first is not None and first <= 5),
        "hit_at_50": float(first is not None and first <= CANDIDATE_DEPTH),
        "mrr_at_50": 0.0 if first is None else 1.0 / first,
        "ndcg_at_5": 0.0 if ideal_dcg == 0.0 else dcg / ideal_dcg,
    }


def aggregate(rows: Iterable[dict[str, float]]) -> dict[str, float]:
    materialized = list(rows)
    if not materialized:
        raise ValueError("cannot aggregate an empty metric collection")
    return {
        key: float(np.mean([row[key] for row in materialized]))
        for key in materialized[0]
    }


def paired_bootstrap(
    treatment: list[float],
    control: list[float],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float]:
    if len(treatment) != len(control) or not treatment:
        raise ValueError("paired bootstrap requires equal non-empty vectors")
    deltas = np.asarray(treatment, dtype=np.float64) - np.asarray(control, dtype=np.float64)
    rng = np.random.default_rng(seed)
    sampled = np.empty(iterations, dtype=np.float64)
    for index in range(iterations):
        sampled[index] = deltas[rng.integers(0, len(deltas), len(deltas))].mean()
    return {
        "delta_mean": float(deltas.mean()),
        "delta_ci_95_low": float(np.quantile(sampled, 0.025)),
        "delta_ci_95_high": float(np.quantile(sampled, 0.975)),
    }
