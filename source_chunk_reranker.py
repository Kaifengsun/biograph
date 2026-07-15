"""Deterministic query-routed reranking over canonical source chunks only."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np

from adaptive_text_first import document_aliases


RRF_K = 60
TABLE_TERMS = {
    "table", "tables", "threshold", "thresholds", "storage condition",
    "storage conditions", "maximum daily dose", "pde", "concentration limit",
    "concentration limits", "acceptance criterion", "acceptance criteria",
    "validation characteristic", "validation characteristics",
}
HIERARCHY_TERMS = {
    "section", "sections", "chapter", "chapters", "appendix", "annex",
    "part", "parts", "structure", "organised", "organized", "lifecycle stages",
    "which document", "which guideline", "where does", "under which",
}
GRAPH_TERMS = {
    "active ingredient", "api", "drug", "drugs", "ndc", "manufacturer",
    "manufacturers", "shortage", "shortages", "unavailable", "supplier",
    "suppliers", "manufactured by", "contains api", "ingredient",
}


@dataclass(frozen=True)
class RerankParameters:
    lexical_bm25_weight: float = 1.0
    semantic_dense_weight: float = 1.0
    explicit_document_weight: float = 0.0
    table_weight: float = 0.0
    hierarchy_weight: float = 0.0


@dataclass(frozen=True)
class SelectiveParameters:
    table_support_depth: int = 5
    table_support_threshold: int = 2
    table_weight: float = 0.25


def tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(value).casefold())


def source_text(record: dict[str, Any], max_chars: int = 2000) -> str:
    text = "\n".join(
        str(record.get(key, "")).strip()
        for key in ("parents_context", "heading", "content")
        if str(record.get(key, "")).strip()
    )
    return text[:max_chars]


@dataclass
class BM25Index:
    ids: list[str]
    term_frequencies: list[Counter[str]]
    document_lengths: np.ndarray
    document_frequency: Counter[str]
    average_length: float
    k1: float = 1.2
    b: float = 0.75

    @classmethod
    def build(cls, records: list[dict[str, Any]], k1: float = 1.2, b: float = 0.75) -> "BM25Index":
        ids: list[str] = []
        frequencies: list[Counter[str]] = []
        lengths: list[int] = []
        document_frequency: Counter[str] = Counter()
        for row in records:
            row_tokens = tokenize(source_text(row))
            term_frequency = Counter(row_tokens)
            ids.append(str(row["chunk_id"]))
            frequencies.append(term_frequency)
            lengths.append(len(row_tokens))
            document_frequency.update(term_frequency.keys())
        values = np.asarray(lengths, dtype=np.float64)
        return cls(ids, frequencies, values, document_frequency, float(values.mean()), k1, b)

    def rank(self, query: str, limit: int = 60) -> list[str]:
        query_terms = Counter(tokenize(query))
        scores = np.zeros(len(self.ids), dtype=np.float64)
        count = len(self.ids)
        for term, query_weight in query_terms.items():
            frequency_docs = self.document_frequency.get(term, 0)
            if not frequency_docs:
                continue
            inverse_document_frequency = math.log(
                1.0 + (count - frequency_docs + 0.5) / (frequency_docs + 0.5)
            )
            for index, term_frequency in enumerate(self.term_frequencies):
                frequency = term_frequency.get(term, 0)
                if not frequency:
                    continue
                norm = frequency + self.k1 * (
                    1.0 - self.b + self.b * self.document_lengths[index] / self.average_length
                )
                scores[index] += (
                    query_weight * inverse_document_frequency * frequency * (self.k1 + 1.0) / norm
                )
        ranked = sorted(range(count), key=lambda index: (-scores[index], index))
        return [self.ids[index] for index in ranked[:limit] if scores[index] > 0.0]


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def token_phrase_present(normalized_text: str, phrase: str) -> bool:
    return f" {normalize(phrase)} " in f" {normalized_text} "


def explicit_document_ids(query: str, document_ids: Iterable[str]) -> set[str]:
    normalized_query = normalize(query)
    return {
        doc_id
        for doc_id in document_ids
        if any(token_phrase_present(normalized_query, alias) for alias in document_aliases(doc_id))
    }


def route_query(query: str, document_ids: Iterable[str]) -> dict[str, Any]:
    normalized_query = normalize(query)
    explicit_docs = explicit_document_ids(query, document_ids)
    if any(token_phrase_present(normalized_query, term) for term in TABLE_TERMS):
        text_route = "table"
    elif any(token_phrase_present(normalized_query, term) for term in HIERARCHY_TERMS):
        text_route = "hierarchy"
    elif explicit_docs:
        text_route = "lexical"
    else:
        text_route = "semantic"
    graph_enabled = any(token_phrase_present(normalized_query, term) for term in GRAPH_TERMS)
    return {
        "text_route": text_route,
        "graph_enabled": graph_enabled,
        "explicit_document_ids": sorted(explicit_docs),
    }


def ordered_union(*rankings: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ranking in rankings:
        for chunk_id in ranking:
            if chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                result.append(chunk_id)
    return result


def reciprocal_rank(rank_lookup: dict[str, int], chunk_id: str, k: int = RRF_K) -> float:
    rank = rank_lookup.get(chunk_id)
    return 0.0 if rank is None else 1.0 / (k + rank)


def is_table_chunk(record: dict[str, Any], table_chunk_ids: set[str]) -> bool:
    chunk_id = str(record.get("chunk_id", ""))
    heading = normalize(str(record.get("heading", "")))
    content_prefix = normalize(str(record.get("content", ""))[:800])
    return (
        chunk_id in table_chunk_ids
        or token_phrase_present(heading, "table")
        or token_phrase_present(content_prefix, "table")
    )


def rerank_source_chunks(
    query: str,
    bm25_ranking: list[str],
    dense_ranking: list[str],
    records_by_id: dict[str, dict[str, Any]],
    selected_documents: list[str] | None,
    table_chunk_ids: set[str],
    parameters: RerankParameters,
    candidate_depth: int = 30,
) -> dict[str, Any]:
    """Rerank the top-N union and return a complete score audit."""
    bm25_candidates = list(dict.fromkeys(bm25_ranking))[:candidate_depth]
    dense_candidates = list(dict.fromkeys(dense_ranking))[:candidate_depth]
    candidates = ordered_union(bm25_candidates, dense_candidates)
    missing = [chunk_id for chunk_id in candidates if chunk_id not in records_by_id]
    if missing:
        raise ValueError(f"non-source or unknown chunk IDs in candidates: {missing[:3]}")

    document_ids = {str(row.get("doc_id", "")) for row in records_by_id.values()}
    route = route_query(query, document_ids)
    explicit_docs = set(route["explicit_document_ids"])
    bm25_rank = {chunk_id: rank for rank, chunk_id in enumerate(bm25_candidates, 1)}
    dense_rank = {chunk_id: rank for rank, chunk_id in enumerate(dense_candidates, 1)}
    selected_rank = {
        doc_id: rank for rank, doc_id in enumerate(dict.fromkeys(selected_documents or []), 1)
    }

    rows: list[dict[str, Any]] = []
    for chunk_id in candidates:
        record = records_by_id[chunk_id]
        doc_id = str(record.get("doc_id", ""))
        features = {
            "bm25_rr": reciprocal_rank(bm25_rank, chunk_id),
            "dense_rr": reciprocal_rank(dense_rank, chunk_id),
            "explicit_document": float(doc_id in explicit_docs),
            "table_indicator": float(is_table_chunk(record, table_chunk_ids)),
            "selected_document_rr": (
                0.0 if doc_id not in selected_rank else 1.0 / (RRF_K + selected_rank[doc_id])
            ),
        }
        bm25_weight = (
            parameters.lexical_bm25_weight if route["text_route"] == "lexical" else 1.0
        )
        dense_weight = (
            parameters.semantic_dense_weight if route["text_route"] == "semantic" else 1.0
        )
        contributions = {
            "bm25": bm25_weight * features["bm25_rr"],
            "dense": dense_weight * features["dense_rr"],
            "explicit_document": parameters.explicit_document_weight * features["explicit_document"] / 61.0,
            "table": (
                parameters.table_weight * features["table_indicator"] / 61.0
                if route["text_route"] == "table" else 0.0
            ),
            "hierarchy": (
                parameters.hierarchy_weight * features["selected_document_rr"]
                if route["text_route"] == "hierarchy" else 0.0
            ),
        }
        rows.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "bm25_rank": bm25_rank.get(chunk_id),
            "dense_rank": dense_rank.get(chunk_id),
            "features": features,
            "contributions": contributions,
            "score": sum(contributions.values()),
        })

    rows.sort(key=lambda row: (
        -row["score"],
        row["bm25_rank"] if row["bm25_rank"] is not None else math.inf,
        row["dense_rank"] if row["dense_rank"] is not None else math.inf,
        row["chunk_id"],
    ))
    protected = False
    if route["text_route"] == "lexical" and parameters.lexical_bm25_weight > 1.0 and bm25_candidates:
        top_bm25 = bm25_candidates[0]
        position = next(index for index, row in enumerate(rows) if row["chunk_id"] == top_bm25)
        if position:
            rows.insert(0, rows.pop(position))
            protected = True

    return {
        "ranking": [row["chunk_id"] for row in rows],
        "route": route,
        "parameters": asdict(parameters),
        "candidate_depth": candidate_depth,
        "protected_bm25_top1": protected,
        "score_audit": rows,
    }


def selective_rerank_source_chunks(
    query: str,
    bm25_ranking: list[str],
    dense_ranking: list[str],
    records_by_id: dict[str, dict[str, Any]],
    selected_documents: list[str] | None,
    table_chunk_ids: set[str],
    parameters: SelectiveParameters,
    candidate_depth: int = 30,
) -> dict[str, Any]:
    """Keep BM25 unchanged unless an auditable table-evidence gate enables fusion."""
    base = rerank_source_chunks(
        query, bm25_ranking, dense_ranking, records_by_id, selected_documents,
        table_chunk_ids, RerankParameters(), candidate_depth,
    )
    bm25_unique = list(dict.fromkeys(bm25_ranking))
    dense_unique = list(dict.fromkeys(dense_ranking))
    support_pool = ordered_union(
        bm25_unique[:parameters.table_support_depth],
        dense_unique[:parameters.table_support_depth],
    )
    support_ids = [chunk_id for chunk_id in support_pool if chunk_id in table_chunk_ids]
    explicit_table_intent = base["route"]["text_route"] == "table"
    enabled = explicit_table_intent or len(support_ids) >= parameters.table_support_threshold
    if not enabled:
        return {
            "ranking": bm25_unique,
            "route": base["route"],
            "parameters": asdict(parameters),
            "candidate_depth": candidate_depth,
            "table_gate": {
                "enabled": False,
                "reason": "insufficient_table_support",
                "explicit_table_intent": explicit_table_intent,
                "support_chunk_ids": support_ids,
            },
            "score_audit": base["score_audit"],
        }

    rows = []
    for source_row in base["score_audit"]:
        row = dict(source_row)
        contributions = {
            "bm25": source_row["features"]["bm25_rr"],
            "dense": source_row["features"]["dense_rr"],
            "table": parameters.table_weight * source_row["features"]["table_indicator"] / 61.0,
        }
        row["contributions"] = contributions
        row["score"] = sum(contributions.values())
        rows.append(row)
    rows.sort(key=lambda row: (
        -row["score"],
        row["bm25_rank"] if row["bm25_rank"] is not None else math.inf,
        row["dense_rank"] if row["dense_rank"] is not None else math.inf,
        row["chunk_id"],
    ))
    return {
        "ranking": [row["chunk_id"] for row in rows],
        "route": base["route"],
        "parameters": asdict(parameters),
        "candidate_depth": candidate_depth,
        "table_gate": {
            "enabled": True,
            "reason": "explicit_table_intent" if explicit_table_intent else "candidate_table_support",
            "explicit_table_intent": explicit_table_intent,
            "support_chunk_ids": support_ids,
        },
        "score_audit": rows,
    }
