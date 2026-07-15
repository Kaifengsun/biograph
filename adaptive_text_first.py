"""Deterministic text-first fusion with auditable metadata and graph gates."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable


TABLE_QUERY_TERMS = {
    "table", "threshold", "thresholds", "storage condition", "storage conditions",
    "maximum daily dose", "pde", "concentration limit", "concentration limits",
    "acceptance criterion", "acceptance criteria", "validation characteristic",
    "validation characteristics",
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "of", "on", "or", "should", "the", "to", "what", "when", "which",
    "with",
}


@dataclass(frozen=True)
class AdaptiveParameters:
    rrf_k: int = 60
    bottom_up_weight: float = 1.0
    top_down_weight: float = 1.0
    graph_weight: float = 0.35
    explicit_document_boost: float = 0.006
    table_boost: float = 0.004
    heading_overlap_boost: float = 0.003
    retain_text_top_n: int = 1


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) > 1 and token not in STOPWORDS}


def _evidence_rows(retrieval: dict[str, Any], route: str) -> list[dict[str, Any]]:
    value = retrieval.get(route) or []
    if isinstance(value, dict):
        value = value.get("evidence") or []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in value:
        chunk_id = str(row.get("chunk_id", ""))
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            rows.append(row)
    return rows


def document_aliases(doc_id: str) -> set[str]:
    normalized = _normalize(doc_id.replace("_", " "))
    parts = normalized.split()
    aliases = {normalized}
    if parts and parts[0] in {"ich", "ema", "fda", "who"} and len(parts) > 1:
        aliases.add(" ".join(parts[1:]))
    if parts[:3] == ["ema", "gmp", "annex"] and len(parts) >= 4:
        aliases.add("annex " + parts[3])
    if parts[:2] == ["fda", "cgmp"]:
        aliases.update({"fda cgmp", "cgmp guidance"})
    if parts and parts[0] == "ich" and len(parts) >= 2:
        aliases.add("ich " + parts[1])
        aliases.add(parts[1])
    return {alias for alias in aliases if len(alias) >= 2}


def explicit_document_ids(query: str, evidence: Iterable[dict[str, Any]]) -> set[str]:
    normalized_query = f" {_normalize(query)} "
    matches: set[str] = set()
    for row in evidence:
        doc_id = str(row.get("doc_id", ""))
        if not doc_id:
            continue
        if any(f" {alias} " in normalized_query for alias in document_aliases(doc_id)):
            matches.add(doc_id)
    return matches


def is_table_query(query: str) -> bool:
    normalized = _normalize(query)
    return any(term in normalized for term in TABLE_QUERY_TERMS)


def is_table_evidence(row: dict[str, Any]) -> bool:
    heading = _normalize(str(row.get("heading", "")))
    content = str(row.get("content", ""))
    return "table" in heading or "[表:" in content or "table " in _normalize(content[:800])


def graph_gate(retrieval: dict[str, Any], explicit_docs: set[str]) -> tuple[bool, str]:
    graph = retrieval.get("graph_path") or {}
    if graph.get("structured_evidence"):
        return True, "direct_structured_record"
    anchors = list(graph.get("anchors") or [])
    if not anchors or not _evidence_rows(retrieval, "graph_path"):
        return False, "no_qualified_graph_anchor"
    anchor_labels = {str(anchor.get("label", "")) for anchor in anchors}
    reachable_docs = set(graph.get("reachable_documents") or [])
    selected_docs = set((retrieval.get("top_down") or {}).get("selected_documents") or [])
    if "RegulatoryDocument" in anchor_labels:
        return True, "explicit_regulatory_document_anchor"
    if "RegulatoryTopic" in anchor_labels and reachable_docs & (selected_docs | explicit_docs):
        return True, "topic_path_agrees_with_text_route"
    entity_labels = {"Drug", "Ingredient", "Manufacturer", "NDC", "DrugShortage"}
    if anchor_labels & entity_labels and reachable_docs & selected_docs:
        return True, "entity_path_agrees_with_text_route"
    return False, "graph_path_lacks_text_route_agreement"


def _heading_overlap(query: str, row: dict[str, Any]) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    return len(query_tokens & _tokens(str(row.get("heading", "")))) / len(query_tokens)


def _retain_text_routes(
    ranking: list[str],
    required: list[str],
    scores: dict[str, float],
    top_k: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    if top_k <= 0:
        return ranking, []
    result = list(ranking)
    actions: list[dict[str, Any]] = []
    required_set = set(required)
    for chunk_id in required:
        if chunk_id in result[:top_k]:
            continue
        removable = [item for item in result[:top_k] if item not in required_set]
        if not removable:
            continue
        displaced = min(removable, key=lambda item: (scores[item], item))
        displaced_position = result.index(displaced)
        result.remove(chunk_id)
        result.insert(displaced_position, chunk_id)
        result.remove(displaced)
        result.insert(top_k, displaced)
        actions.append({"retained_chunk_id": chunk_id, "displaced_chunk_id": displaced, "rank": displaced_position + 1})
    return result, actions


def adaptive_rank(
    retrieval: dict[str, Any],
    parameters: AdaptiveParameters | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    parameters = parameters or AdaptiveParameters()
    query = str(retrieval.get("query", ""))
    components = {
        route: _evidence_rows(retrieval, route)
        for route in ("bottom_up", "top_down", "graph_path")
    }
    all_rows: dict[str, dict[str, Any]] = {}
    text_chunk_ids: set[str] = set()
    for rows in components.values():
        for row in rows:
            all_rows.setdefault(str(row["chunk_id"]), row)
    for route in ("bottom_up", "top_down"):
        text_chunk_ids.update(str(row["chunk_id"]) for row in components[route])
    explicit_docs = explicit_document_ids(query, all_rows.values())
    table_query = is_table_query(query)
    graph_enabled, graph_reason = graph_gate(retrieval, explicit_docs)
    route_weights = {
        "bottom_up": parameters.bottom_up_weight,
        "top_down": parameters.top_down_weight,
        "graph_path": parameters.graph_weight if graph_enabled else 0.0,
    }
    scores = {chunk_id: 0.0 for chunk_id in all_rows}
    audit_by_chunk: dict[str, dict[str, Any]] = {
        chunk_id: {"route_contributions": {}, "boosts": {}}
        for chunk_id in all_rows
    }
    for route, rows in components.items():
        weight = route_weights[route]
        if weight <= 0:
            continue
        for rank, row in enumerate(rows, 1):
            chunk_id = str(row["chunk_id"])
            contribution = weight / (parameters.rrf_k + rank)
            scores[chunk_id] += contribution
            audit_by_chunk[chunk_id]["route_contributions"][route] = contribution
    for chunk_id, row in all_rows.items():
        if chunk_id not in text_chunk_ids and not graph_enabled:
            continue
        if str(row.get("doc_id", "")) in explicit_docs:
            scores[chunk_id] += parameters.explicit_document_boost
            audit_by_chunk[chunk_id]["boosts"]["explicit_document"] = parameters.explicit_document_boost
        if table_query and is_table_evidence(row):
            scores[chunk_id] += parameters.table_boost
            audit_by_chunk[chunk_id]["boosts"]["table"] = parameters.table_boost
        overlap = _heading_overlap(query, row)
        if overlap:
            boost = parameters.heading_overlap_boost * overlap
            scores[chunk_id] += boost
            audit_by_chunk[chunk_id]["boosts"]["heading_overlap"] = boost
    first_rank: dict[str, int] = {}
    for rows in components.values():
        for rank, row in enumerate(rows, 1):
            chunk_id = str(row["chunk_id"])
            first_rank[chunk_id] = min(first_rank.get(chunk_id, rank), rank)
    eligible_scores = {chunk_id: score for chunk_id, score in scores.items() if score > 0.0}
    ranking = sorted(eligible_scores, key=lambda chunk_id: (-eligible_scores[chunk_id], first_rank.get(chunk_id, 10**9), chunk_id))
    required: list[str] = []
    for route in ("bottom_up", "top_down"):
        required.extend(str(row["chunk_id"]) for row in components[route][:parameters.retain_text_top_n])
    required = list(dict.fromkeys(required))
    ranking, retention_actions = _retain_text_routes(ranking, required, scores, top_k)
    return {
        "query": query,
        "ranking": ranking,
        "top_k": ranking[:top_k],
        "parameters": asdict(parameters),
        "audit": {
            "explicit_document_ids": sorted(explicit_docs),
            "table_query": table_query,
            "graph_gate": {"enabled": graph_enabled, "reason": graph_reason},
            "route_weights": route_weights,
            "required_text_chunks": required,
            "retention_actions": retention_actions,
            "chunks": {
                chunk_id: {"score": eligible_scores[chunk_id], **audit_by_chunk[chunk_id]}
                for chunk_id in ranking
            },
        },
    }
