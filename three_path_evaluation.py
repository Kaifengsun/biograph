"""Validation and metrics helpers for frozen three-path retrieval experiments."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from build_regulatory_evidence_graph import normalize_alias


FROZEN_STATUS = "frozen_human_reviewed_evaluation_set"
VARIANTS = ("bottom_up", "top_down", "graph_path", "three_path_rrf")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_ids(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return list(dict.fromkeys(part.strip() for part in text.replace("\n", ";").split(";") if part.strip()))


def split_path_nodes(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return list(dict.fromkeys(part.strip() for part in text.replace("\n", " -> ").split("->") if part.strip()))


def ranked_chunk_ids(retrieval: dict[str, Any], variant: str) -> list[str]:
    if variant == "bottom_up":
        rows = retrieval.get("bottom_up") or []
        return _dedupe_item_ids(rows)
    if variant == "top_down":
        rows = (retrieval.get("top_down") or {}).get("evidence") or []
        return _dedupe_item_ids(rows)
    if variant == "graph_path":
        rows = (retrieval.get("graph_path") or {}).get("evidence") or []
        return _dedupe_item_ids(rows)
    if variant == "three_path_rrf":
        components = [
            ranked_chunk_ids(retrieval, "bottom_up"),
            ranked_chunk_ids(retrieval, "top_down"),
            ranked_chunk_ids(retrieval, "graph_path"),
        ]
        scores: dict[str, float] = defaultdict(float)
        first_rank: dict[str, int] = {}
        for rows in components:
            for rank, chunk_id in enumerate(rows, 1):
                scores[chunk_id] += 1.0 / (60 + rank)
                first_rank[chunk_id] = min(first_rank.get(chunk_id, rank), rank)
        return [chunk_id for chunk_id, _ in sorted(scores.items(), key=lambda item: (-item[1], first_rank[item[0]], item[0]))]
    raise ValueError(f"unknown variant: {variant}")


def _dedupe_item_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(row.get("chunk_id", "")).strip() for row in rows if str(row.get("chunk_id", "")).strip()))


def reciprocal_rank(ranked_ids: list[str], gold_ids: set[str]) -> float:
    for rank, chunk_id in enumerate(ranked_ids, 1):
        if chunk_id in gold_ids:
            return 1.0 / rank
    return 0.0


def hit_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    return float(any(chunk_id in gold_ids for chunk_id in ranked_ids[:k]))


def ndcg_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    if not gold_ids:
        return 0.0
    dcg = sum(1.0 / math.log2(rank + 1) for rank, chunk_id in enumerate(ranked_ids[:k], 1) if chunk_id in gold_ids)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, len(gold_ids)) + 1))
    return dcg / ideal if ideal else 0.0


def contiguous_subsequence(needle: list[str], haystack: list[str]) -> bool:
    if not needle:
        return False
    width = len(needle)
    return any(haystack[index:index + width] == needle for index in range(len(haystack) - width + 1))


def validate_frozen_pack(pack: dict[str, Any]) -> list[dict[str, Any]]:
    if pack.get("status") != FROZEN_STATUS or pack.get("formal_metrics_ready") is not True:
        raise ValueError("formal evaluation requires a frozen, human-reviewed evaluation snapshot")
    rows = list(pack.get("queries") or [])
    if not rows:
        raise ValueError("frozen evaluation snapshot contains no queries")
    seen = set()
    for row in rows:
        annotation_id = str(row.get("annotation_id", ""))
        if not annotation_id or annotation_id in seen:
            raise ValueError(f"invalid or duplicate annotation_id: {annotation_id!r}")
        seen.add(annotation_id)
        if row.get("review_status") != "reviewed" or not row.get("eligible_for_formal_evaluation"):
            raise ValueError(f"ineligible row present in frozen snapshot: {annotation_id}")
        if not row.get("gold_evidence_chunk_ids"):
            raise ValueError(f"frozen row has no gold evidence: {annotation_id}")
    return rows


def evaluate_retrieval(rows: list[dict[str, Any]], retrieval_rows: list[dict[str, Any]], k_values: tuple[int, ...] = (1, 3, 5)) -> dict[str, Any]:
    retrieval_by_query: dict[str, dict[str, Any]] = {}
    for record in retrieval_rows:
        retrieval = record.get("retrieval") or {}
        key = normalize_alias(str(retrieval.get("query", "")))
        if not key:
            continue
        if key in retrieval_by_query:
            raise ValueError(f"duplicate retrieval query after normalization: {retrieval.get('query')!r}")
        retrieval_by_query[key] = retrieval

    per_query = []
    for row in rows:
        retrieval = retrieval_by_query.get(normalize_alias(str(row["query"])))
        if retrieval is None:
            raise ValueError(f"missing retrieval output for {row['annotation_id']}")
        gold_ids = set(row["gold_evidence_chunk_ids"])
        variant_metrics = {}
        for variant in VARIANTS:
            ranked_ids = ranked_chunk_ids(retrieval, variant)
            variant_metrics[variant] = {
                "ranked_chunk_ids": ranked_ids,
                "mrr": reciprocal_rank(ranked_ids, gold_ids),
                **{f"hit_at_{k}": hit_at_k(ranked_ids, gold_ids, k) for k in k_values},
                **{f"ndcg_at_{k}": ndcg_at_k(ranked_ids, gold_ids, k) for k in k_values},
            }
        accepted_path = list(row.get("accepted_graph_path_node_ids") or [])
        graph_result = retrieval.get("graph_path") or {}
        # Regulatory-document paths and structured event paths are separate
        # evidence modalities.  Apply the top-five cutoff within each modality
        # so a long document-path list cannot hide a ranked structured path.
        paths = list(graph_result.get("paths") or [])[:5] + list(graph_result.get("structured_paths") or [])[:5]
        per_query.append({
            "annotation_id": row["annotation_id"],
            "query_slice": row["query_slice"],
            "gold_evidence_chunk_ids": sorted(gold_ids),
            "variants": variant_metrics,
            "graph_path_checked": bool(accepted_path),
            "graph_path_success_at_5": any(contiguous_subsequence(accepted_path, path.get("node_ids") or []) for path in paths) if accepted_path else None,
        })

    aggregate = {variant: aggregate_variant(per_query, variant, k_values) for variant in VARIANTS}
    by_slice = {}
    for query_slice in sorted({row["query_slice"] for row in per_query}):
        subset = [row for row in per_query if row["query_slice"] == query_slice]
        by_slice[query_slice] = {variant: aggregate_variant(subset, variant, k_values) for variant in VARIANTS}
    path_rows = [row for row in per_query if row["graph_path_checked"]]
    return {
        "query_count": len(per_query),
        "k_values": list(k_values),
        "fusion": "reciprocal_rank_fusion(k=60) over fixed bottom_up, top_down, graph_path rankings",
        "graph_path_validation_policy": "accepted node chains may match a top-5 regulatory-document path or a top-5 structured-event path; structured nodes are excluded from text-retrieval metrics",
        "aggregate": aggregate,
        "by_slice": by_slice,
        "graph_path_validation": {
            "checked_count": len(path_rows),
            "success_at_5": (sum(bool(row["graph_path_success_at_5"]) for row in path_rows) / len(path_rows)) if path_rows else None,
        },
        "per_query": per_query,
    }


def aggregate_variant(rows: list[dict[str, Any]], variant: str, k_values: tuple[int, ...]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "mrr": None, **{f"hit_at_{k}": None for k in k_values}, **{f"ndcg_at_{k}": None for k in k_values}}
    values = [row["variants"][variant] for row in rows]
    return {
        "n": len(values),
        "mrr": round(sum(item["mrr"] for item in values) / len(values), 6),
        **{f"hit_at_{k}": round(sum(item[f"hit_at_{k}"] for item in values) / len(values), 6) for k in k_values},
        **{f"ndcg_at_{k}": round(sum(item[f"ndcg_at_{k}"] for item in values) / len(values), 6) for k in k_values},
    }


def review_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_rows": len(rows),
        "by_status": dict(sorted(Counter(str(row.get("review_status", "")) for row in rows).items())),
        "by_slice": dict(sorted(Counter(str(row.get("query_slice", "")) for row in rows).items())),
        "eligible_rows": sum(bool(row.get("eligible_for_formal_evaluation")) for row in rows),
    }
