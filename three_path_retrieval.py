"""Deterministic three-path retrieval over the build5 evidence graph snapshot.

This module deliberately does not import the legacy Neo4j-backed retriever.
All graph traversal is performed over the immutable JSONL snapshot, while
FAISS is used only for R2 source evidence and R3 HyDE document navigation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from build_regulatory_evidence_graph import normalize_alias, read_jsonl, sha256_file


DEFAULT_GRAPH = Path("artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda")
DEFAULT_CORPUS = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
DEFAULT_INDEX_ROOT = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")

GRAPH_RELATION_ALLOWLIST = {
    "CONTAINS", "PARENT_OF", "NEXT", "MENTIONS", "REFERENCES", "COVERS_TOPIC",
    "SUPERSEDES", "COMPLEMENTS", "USES_PRINCIPLES_FROM", "APPLIES_DEFINITION_FROM",
    "INTERPRETS", "REQUIRES_COMPLIANCE_WITH", "CONTAINS_API", "SUPPLIED_BY",
    "SUBSTITUTE_OF", "BELONGS_TO_AREA", "WAS_RECALLED", "RECALLED_BY",
    "AFFECTS_NDC_PRODUCT", "REPORTED_BY", "HAS_ACTIVE_INGREDIENT", "SAME_AS_CANDIDATE",
}

ANCHOR_LABELS = {
    "Drug", "API", "Manufacturer", "Country", "TherapeuticArea", "DrugClass",
    "Regulation", "ShortageEvent", "RecallEvent", "FDA_DrugShortageEvent",
    "FDANDCProduct", "FDAManufacturer", "FDAActiveIngredient", "RegulatoryDocument",
    "RegulatoryTopic", "RegulatoryReference",
}

RELATION_EXPANSION_PRIORITY = {
    "MENTIONS": 0,
    "SAME_AS_CANDIDATE": 1,
    "AFFECTS_NDC_PRODUCT": 2,
    "HAS_ACTIVE_INGREDIENT": 2,
    "REPORTED_BY": 2,
    "CONTAINS_API": 3,
    "SUPPLIED_BY": 3,
    "SUBSTITUTE_OF": 3,
    "BELONGS_TO_AREA": 3,
    "REFERENCES": 3,
    "SUPERSEDES": 3,
    "COMPLEMENTS": 3,
    "USES_PRINCIPLES_FROM": 3,
    "APPLIES_DEFINITION_FROM": 3,
    "COVERS_TOPIC": 3,
    "INTERPRETS": 3,
    "REQUIRES_COMPLIANCE_WITH": 3,
    "WAS_RECALLED": 4,
    "RECALLED_BY": 4,
    "PARENT_OF": 5,
    "CONTAINS": 6,
    "NEXT": 7,
}


@dataclass(frozen=True)
class EvidenceItem:
    chunk_id: str
    doc_id: str
    heading: str
    content: str
    score: float
    route: str
    route_details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "heading": self.heading,
            "content": self.content,
            "score": round(self.score, 6),
            "route": self.route,
            "route_details": self.route_details,
        }


@dataclass(frozen=True)
class GraphPath:
    node_ids: list[str]
    nodes: list[dict[str, str]]
    edges: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"node_ids": self.node_ids, "nodes": self.nodes, "edges": self.edges, "depth": len(self.edges)}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class ThreePathSnapshotRetriever:
    """Retrieve source chunks through bottom-up, top-down, and graph paths."""

    def __init__(
        self,
        graph_dir: Path = DEFAULT_GRAPH,
        corpus_dir: Path = DEFAULT_CORPUS,
        index_root: Path = DEFAULT_INDEX_ROOT,
        embed_queries: Callable[[list[str]], np.ndarray] | None = None,
    ) -> None:
        self.graph_dir = Path(graph_dir)
        self.corpus_dir = Path(corpus_dir)
        self.index_root = Path(index_root)
        self._embed_queries = embed_queries
        self._embedding_client: Any | None = None
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.chunk_store: dict[str, dict[str, Any]] = {}
        self.children_by_parent: dict[str, list[str]] = defaultdict(list)
        self.parent_by_child: dict[str, str] = {}
        self.doc_roots: dict[str, list[str]] = defaultdict(list)
        self.adjacency: dict[str, list[tuple[str, dict[str, Any], bool]]] = defaultdict(list)
        self.alias_index: dict[str, list[str]] = defaultdict(list)
        self._faiss: dict[str, Any] = {}
        self._meta: dict[str, list[dict[str, Any]]] = {}
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        nodes_path = self.graph_dir / "nodes.jsonl"
        edges_path = self.graph_dir / "edges.jsonl"
        if not nodes_path.exists() or not edges_path.exists():
            raise FileNotFoundError(f"missing graph JSONL in {self.graph_dir}")
        self.nodes = {node["id"]: node for node in read_jsonl(nodes_path)}
        self.edges = read_jsonl(edges_path)
        self._load_chunk_store()
        for edge in self.edges:
            source, target, relation = edge["source"], edge["target"], edge["relation"]
            if source not in self.nodes or target not in self.nodes:
                raise ValueError(f"dangling graph edge: {source} -[{relation}]-> {target}")
            if relation == "PARENT_OF":
                self.children_by_parent[source].append(target)
                if target in self.parent_by_child:
                    raise ValueError(f"multiple tree parents for {target}")
                self.parent_by_child[target] = source
            elif relation == "CONTAINS" and source.startswith("regdoc:") and target.startswith("chunk:"):
                self.doc_roots[source.removeprefix("regdoc:")].append(target)
            if relation in GRAPH_RELATION_ALLOWLIST:
                self.adjacency[source].append((target, edge, True))
                self.adjacency[target].append((source, edge, False))
        for node_id, node in self.nodes.items():
            label = str(node.get("label", ""))
            if label not in ANCHOR_LABELS:
                continue
            name = str(node.get("name", ""))
            aliases = {normalize_alias(name)}
            if label == "RegulatoryDocument":
                doc_id = str((node.get("properties") or {}).get("doc_id", ""))
                aliases.add(normalize_alias(doc_id.replace("_", " ")))
            for alias in aliases:
                if len(alias) >= 3:
                    self.alias_index[alias].append(node_id)

    def _load_chunk_store(self) -> None:
        if not self.corpus_dir.exists():
            raise FileNotFoundError(self.corpus_dir)
        for path in sorted(self.corpus_dir.glob("*_enriched.json")):
            rows = _read_json(path)
            for row in rows:
                chunk_id = str(row.get("chunk_id", ""))
                if chunk_id:
                    self.chunk_store[chunk_id] = row
        graph_chunk_ids = {node_id.removeprefix("chunk:") for node_id, node in self.nodes.items() if node.get("label") == "DocChunk"}
        missing = graph_chunk_ids - set(self.chunk_store)
        if missing:
            raise ValueError(f"graph chunks absent from frozen source corpus: {len(missing)}")

    def input_hashes(self) -> dict[str, str]:
        return {
            "graph_nodes": sha256_file(self.graph_dir / "nodes.jsonl"),
            "graph_edges": sha256_file(self.graph_dir / "edges.jsonl"),
            "r2_metadata": sha256_file(self.index_root / "R2_summary" / "pharma_docs.meta.json"),
            "r3_metadata": sha256_file(self.index_root / "R3_hyde" / "pharma_docs.meta.json"),
        }

    def _load_variant(self, variant: str) -> tuple[Any, list[dict[str, Any]]]:
        if variant in self._faiss:
            return self._faiss[variant], self._meta[variant]
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError("FAISS is required for snapshot retrieval") from exc
        variant_dir = self.index_root / variant
        index_path = variant_dir / "pharma_docs.faiss"
        meta_path = variant_dir / "pharma_docs.meta.json"
        if not index_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"missing {variant} retrieval artifact")
        self._faiss[variant] = faiss.read_index(str(index_path))
        self._meta[variant] = _read_json(meta_path)
        return self._faiss[variant], self._meta[variant]

    def _default_embed_queries(self, queries: list[str]) -> np.ndarray:
        from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
        from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient

        if self._embedding_client is None:
            settings = PipelineSettings()
            settings.embedding = EmbeddingConfig(
                backend="local",
                local_model=settings.embedding.local_model,
                dimension=settings.embedding.dimension,
            )
            self._embedding_client = EmbeddingClient(settings.embedding)
        return self._embedding_client.embed(queries, batch_size=min(8, len(queries)))

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        if not queries:
            raise ValueError("queries must not be empty")
        embedder = self._embed_queries or self._default_embed_queries
        vectors = np.asarray(embedder(queries), dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(queries):
            raise ValueError("query embedder must return a (n_queries, dimension) array")
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError("FAISS is required for query normalization") from exc
        faiss.normalize_L2(vectors)
        return vectors

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode_queries([query])

    def rank_variant(
        self,
        variant: str,
        query: str,
        k: int,
        query_vector: np.ndarray | None = None,
    ) -> list[dict[str, Any]]:
        index, metadata = self._load_variant(variant)
        vector = query_vector if query_vector is not None else self.encode_query(query)
        scores, positions = index.search(np.array(vector, dtype=np.float32, copy=True), min(k, index.ntotal))
        rows: list[dict[str, Any]] = []
        for rank, (score, position) in enumerate(zip(scores[0], positions[0]), 1):
            if position < 0 or position >= len(metadata):
                continue
            rows.append({**metadata[position], "vector_score": float(score), "vector_rank": rank})
        return rows

    @staticmethod
    def _dedupe_chunk_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[str, dict[str, Any]] = {}
        for record in records:
            chunk_id = str(record.get("chunk_id", ""))
            if not chunk_id:
                continue
            previous = best.get(chunk_id)
            if previous is None or float(record.get("vector_score", 0.0)) > float(previous.get("vector_score", 0.0)):
                best[chunk_id] = record
        return sorted(best.values(), key=lambda row: (-float(row.get("vector_score", 0.0)), int(row.get("vector_rank", 10**9))))

    def _evidence(self, chunk_id: str, score: float, route: str, details: dict[str, Any]) -> EvidenceItem:
        source = self.chunk_store[chunk_id]
        return EvidenceItem(
            chunk_id=chunk_id,
            doc_id=str(source.get("doc_id", "")),
            heading=str(source.get("heading", "")),
            content=str(source.get("content", "")),
            score=score,
            route=route,
            route_details=details,
        )

    def bottom_up_from_rankings(self, r2_rows: Iterable[dict[str, Any]], k: int = 5) -> list[EvidenceItem]:
        """Return only R2 source-chunk evidence; no HyDE sidecar can occupy evidence rank."""
        result = []
        for row in self._dedupe_chunk_records(r2_rows):
            chunk_id = str(row["chunk_id"])
            if chunk_id not in self.chunk_store:
                continue
            result.append(self._evidence(chunk_id, float(row.get("vector_score", 0.0)), "bottom_up_r2_source", {
                "r2_rank": int(row.get("vector_rank", 0)),
                "representation_type": row.get("type", "summary"),
            }))
            if len(result) >= k:
                break
        return result

    def bottom_up_search(self, query: str, k: int = 5) -> list[EvidenceItem]:
        return self.bottom_up_from_rankings(self.rank_variant("R2_summary", query, 100), k=k)

    def _section_chain(self, chunk_node_id: str) -> list[str]:
        chain = [chunk_node_id]
        current = chunk_node_id
        while current in self.parent_by_child:
            current = self.parent_by_child[current]
            chain.append(current)
        return list(reversed(chain))

    def top_down_from_rankings(
        self,
        r3_rows: Iterable[dict[str, Any]],
        r2_rows: Iterable[dict[str, Any]],
        k: int = 5,
        document_budget: int = 2,
    ) -> dict[str, Any]:
        """Use R3 only to route to documents, then R2 to select source chunks."""
        vote_scores: Counter[str] = Counter()
        for row in r3_rows:
            doc_id = str(row.get("doc_id", ""))
            if doc_id:
                vote_scores[doc_id] += 1.0 / max(1, int(row.get("vector_rank", 1)))
        selected_docs = [doc_id for doc_id, _score in vote_scores.most_common(document_budget)]
        candidates = [row for row in self._dedupe_chunk_records(r2_rows) if row.get("doc_id") in selected_docs]
        evidence_by_chunk: dict[str, EvidenceItem] = {}
        route_nodes: list[dict[str, Any]] = []
        for row in candidates:
            chunk_id = str(row.get("chunk_id", ""))
            if chunk_id not in self.chunk_store:
                continue
            node_id = f"chunk:{chunk_id}"
            chain = self._section_chain(node_id) if node_id in self.nodes else []
            route_nodes.append({"doc_id": row.get("doc_id"), "chunk_chain": chain})
            evidence_by_chunk.setdefault(chunk_id, self._evidence(chunk_id, float(row.get("vector_score", 0.0)), "top_down_r3_route_then_r2_source", {
                "selected_documents": selected_docs,
                "r2_rank": int(row.get("vector_rank", 0)),
                "section_chain": chain,
            }))
            # Structural descent: expose direct children of routed sections as
            # lower-scored candidates, without allowing summaries as evidence.
            for ancestor in chain:
                for child_id in self.children_by_parent.get(ancestor, []):
                    child_chunk_id = child_id.removeprefix("chunk:")
                    if child_chunk_id not in self.chunk_store or child_chunk_id in evidence_by_chunk:
                        continue
                    evidence_by_chunk[child_chunk_id] = self._evidence(child_chunk_id, float(row.get("vector_score", 0.0)) * 0.55, "top_down_structural_descent", {
                        "selected_documents": selected_docs,
                        "descended_from": ancestor,
                        "routed_seed_chunk": chunk_id,
                    })
        evidence = sorted(evidence_by_chunk.values(), key=lambda item: -item.score)[:k]
        return {
            "selected_documents": selected_docs,
            "document_scores": {doc_id: round(vote_scores[doc_id], 6) for doc_id in selected_docs},
            "routing": route_nodes[:20],
            "evidence": evidence,
        }

    def top_down_search(self, query: str, k: int = 5, document_budget: int = 2) -> dict[str, Any]:
        return self.top_down_from_rankings(
            self.rank_variant("R3_hyde", query, 240),
            self.rank_variant("R2_summary", query, 500),
            k=k,
            document_budget=document_budget,
        )

    def entity_anchors(self, query: str) -> list[str]:
        normalized_query = normalize_alias(query)
        padded_query = f" {normalized_query} "
        anchors: list[str] = []
        for alias, node_ids in self.alias_index.items():
            if f" {alias} " in padded_query:
                anchors.extend(node_ids)
        return sorted(set(anchors))

    def _neighbor_priority(self, current: str, neighbor: str, edge: dict[str, Any]) -> tuple[int, int, str]:
        """Prefer direct source evidence before cross-document expansion."""
        relation = edge["relation"]
        current_label = str(self.nodes[current].get("label", ""))
        neighbor_label = str(self.nodes[neighbor].get("label", ""))
        if current_label == "RegulatoryDocument" and relation == "CONTAINS":
            return (-2, 0, neighbor)
        if current_label in ANCHOR_LABELS and neighbor_label == "DocChunk" and relation == "MENTIONS":
            return (-2, 0, neighbor)
        return (RELATION_EXPANSION_PRIORITY.get(relation, 99), 0, neighbor)

    def _structured_event_evidence(self, query: str, anchors: Iterable[str], k: int = 5) -> list[dict[str, Any]]:
        """Expose matched FDA shortage facts without treating them as source chunks.

        These records are intentionally kept separate from ``evidence``.  The
        latter is reserved for frozen regulatory-document passages and is the
        only input to text-retrieval metrics.
        """
        stop_terms = {
            "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "what",
            "according", "available", "availability", "fda", "recorded", "shortage", "snapshot", "with",
        }
        query_terms = {
            term for term in re.findall(r"[a-z0-9]+", normalize_alias(query))
            if term not in stop_terms and len(term) > 2
        }
        # ``normalize_alias`` deliberately removes parenthesized fragments for
        # entity matching, so retain literal NDC-style identifiers for event
        # ranking as well.
        query_codes = {
            re.sub(r"[^a-z0-9]", "", code.lower())
            for code in re.findall(r"\b\d{4,5}-\d{3,5}-\d{1,3}\b", query)
        }
        event_candidates = set(anchors)
        for anchor in anchors:
            for neighbor, _edge, _forward in self.adjacency.get(anchor, []):
                if self.nodes[neighbor].get("label") == "FDA_DrugShortageEvent":
                    event_candidates.add(neighbor)
        rows: list[dict[str, Any]] = []
        for node_id in sorted(event_candidates):
            node = self.nodes[node_id]
            if node.get("label") != "FDA_DrugShortageEvent":
                continue
            properties = dict(node.get("properties") or {})
            searchable_fields = ("generic_name", "company_name", "package_ndc", "availability", "shortage_reason", "status")
            searchable = normalize_alias(" ".join([str(node.get("name", "")), *(str(properties.get(key, "")) for key in searchable_fields)]))
            matched_terms = sorted(term for term in query_terms if term in searchable)
            package_code = re.sub(r"[^a-z0-9]", "", str(properties.get("package_ndc", "")).lower())
            exact_code_match = bool(package_code and package_code in query_codes)
            if not matched_terms and not exact_code_match:
                continue
            next_hops = sorted(
                self.adjacency.get(node_id, []),
                key=lambda item: self._neighbor_priority(node_id, item[0], item[1]),
            )
            path_node_ids = [node_id]
            path_edges: list[dict[str, Any]] = []
            for neighbor, edge, forward in next_hops:
                if edge["relation"] != "AFFECTS_NDC_PRODUCT":
                    continue
                path_node_ids.append(neighbor)
                path_edges.append({
                    "relation": edge["relation"],
                    "source": edge["source"],
                    "target": edge["target"],
                    "traversal_direction": "forward" if forward else "reverse",
                    "provenance": (edge.get("properties") or {}).get("provenance", {}),
                })
                for ingredient, ingredient_edge, ingredient_forward in sorted(
                    self.adjacency.get(neighbor, []),
                    key=lambda item: self._neighbor_priority(neighbor, item[0], item[1]),
                ):
                    if ingredient in path_node_ids or ingredient_edge["relation"] != "HAS_ACTIVE_INGREDIENT":
                        continue
                    path_node_ids.append(ingredient)
                    path_edges.append({
                        "relation": ingredient_edge["relation"],
                        "source": ingredient_edge["source"],
                        "target": ingredient_edge["target"],
                        "traversal_direction": "forward" if ingredient_forward else "reverse",
                        "provenance": (ingredient_edge.get("properties") or {}).get("provenance", {}),
                    })
                    break
                break
            rows.append({
                "node_id": node_id,
                "score": round(float(len(matched_terms) + (100 if exact_code_match else 0)), 6),
                "matched_query_terms": matched_terms,
                "record": {
                    key: properties.get(key, "")
                    for key in ("generic_name", "company_name", "package_ndc", "availability", "shortage_reason", "status", "update_date")
                },
                "path": GraphPath(
                    node_ids=path_node_ids,
                    nodes=[{
                        "id": item_id,
                        "label": str(self.nodes[item_id].get("label", "")),
                        "name": str(self.nodes[item_id].get("name", "")),
                    } for item_id in path_node_ids],
                    edges=path_edges,
                ).to_dict(),
            })
        return sorted(rows, key=lambda row: (-float(row["score"]), str(row["node_id"])))[:k]

    def graph_path_search(
        self,
        query: str,
        k: int = 5,
        max_depth: int = 4,
        max_paths: int = 20,
        max_paths_per_anchor: int = 8,
        max_state_expansions: int = 800,
        max_neighbors_per_node: int = 24,
        source_rows: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        anchors = self.entity_anchors(query)
        structured_evidence = self._structured_event_evidence(query, anchors)
        paths: list[GraphPath] = []
        seen_path_keys: set[tuple[str, ...]] = set()
        queue: deque[tuple[list[str], list[dict[str, Any]], str]] = deque((([anchor], [], anchor)) for anchor in anchors)
        paths_per_anchor: Counter[str] = Counter()
        states_expanded = 0
        states_enqueued = len(queue)
        while queue and len(paths) < max_paths and states_expanded < max_state_expansions:
            node_path, edge_path, root_anchor = queue.popleft()
            states_expanded += 1
            current = node_path[-1]
            if len(edge_path) and self.nodes[current].get("label") == "DocChunk":
                key = tuple(node_path)
                if key not in seen_path_keys and paths_per_anchor[root_anchor] < max_paths_per_anchor:
                    seen_path_keys.add(key)
                    paths_per_anchor[root_anchor] += 1
                    paths.append(GraphPath(
                        node_ids=node_path,
                        nodes=[{"id": node_id, "label": str(self.nodes[node_id].get("label", "")), "name": str(self.nodes[node_id].get("name", ""))} for node_id in node_path],
                        edges=edge_path,
                    ))
                continue
            if len(edge_path) >= max_depth:
                continue
            ordered_neighbors = sorted(
                self.adjacency.get(current, []),
                key=lambda item: self._neighbor_priority(current, item[0], item[1]),
            )
            for neighbor, edge, forward in ordered_neighbors[:max_neighbors_per_node]:
                if neighbor in node_path:
                    continue
                traversal = {
                    "relation": edge["relation"],
                    "source": edge["source"],
                    "target": edge["target"],
                    "traversal_direction": "forward" if forward else "reverse",
                    "provenance": (edge.get("properties") or {}).get("provenance", {}),
                }
                queue.append((node_path + [neighbor], edge_path + [traversal], root_anchor))
                states_enqueued += 1
        evidence_by_chunk: dict[str, EvidenceItem] = {}
        reachable_docs: set[str] = set()
        witness_paths_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for path in paths:
            for node_id in path.node_ids:
                node = self.nodes[node_id]
                if node.get("label") == "RegulatoryDocument":
                    doc_id = str((node.get("properties") or {}).get("doc_id", ""))
                    if doc_id:
                        reachable_docs.add(doc_id)
                        witness_paths_by_doc[doc_id].append(path.to_dict())
            chunk_id = path.node_ids[-1].removeprefix("chunk:")
            if chunk_id not in self.chunk_store:
                continue
            reachable_docs.add(str(self.chunk_store[chunk_id].get("doc_id", "")))
            score = 0.0 if source_rows is not None else 1.0 / max(1, len(path.edges))
            evidence_by_chunk.setdefault(chunk_id, self._evidence(chunk_id, score, "graph_path", {"path": path.to_dict()}))
        # Graph traversal defines the admissible document set. R2 then ranks
        # source chunks within that set, preventing a document preamble from
        # winning simply because it is the first CONTAINS edge encountered.
        if source_rows is not None and reachable_docs:
            for row in self._dedupe_chunk_records(source_rows):
                chunk_id = str(row.get("chunk_id", ""))
                if row.get("doc_id") not in reachable_docs or chunk_id not in self.chunk_store:
                    continue
                evidence_by_chunk[chunk_id] = self._evidence(chunk_id, float(row.get("vector_score", 0.0)), "graph_path_r2_backfill", {
                    "graph_reachable_documents": sorted(reachable_docs),
                    "witness_paths": witness_paths_by_doc.get(str(row.get("doc_id")), [])[:3],
                    "r2_rank": int(row.get("vector_rank", 0)),
                })
        return {
            "anchors": [{"id": node_id, "label": self.nodes[node_id].get("label"), "name": self.nodes[node_id].get("name")} for node_id in anchors],
            "paths": [path.to_dict() for path in paths],
            "structured_evidence": structured_evidence,
            "structured_paths": [row["path"] for row in structured_evidence],
            "reachable_documents": sorted(doc_id for doc_id in reachable_docs if doc_id),
            "evidence": sorted(evidence_by_chunk.values(), key=lambda item: (-item.score, item.chunk_id))[:k],
            "abstained": not paths,
            "search_budget": {
                "max_state_expansions": max_state_expansions,
                "max_paths_per_anchor": max_paths_per_anchor,
                "max_neighbors_per_node": max_neighbors_per_node,
                "states_expanded": states_expanded,
                "states_enqueued": states_enqueued,
                "truncated": bool(queue) and (states_expanded >= max_state_expansions or len(paths) >= max_paths),
            },
        }

    def retrieve_all(
        self,
        query: str,
        k: int = 5,
        document_budget: int = 2,
        max_depth: int = 4,
        max_state_expansions: int = 800,
        query_vector: np.ndarray | None = None,
    ) -> dict[str, Any]:
        query_vector = query_vector if query_vector is not None else self.encode_query(query)
        r2_rows = self.rank_variant("R2_summary", query, 500, query_vector=query_vector)
        r3_rows = self.rank_variant("R3_hyde", query, 240, query_vector=query_vector)
        bottom_up = self.bottom_up_from_rankings(r2_rows, k=k)
        top_down = self.top_down_from_rankings(r3_rows, r2_rows, k=k, document_budget=document_budget)
        graph_path = self.graph_path_search(
            query,
            k=k,
            max_depth=max_depth,
            max_state_expansions=max_state_expansions,
            source_rows=r2_rows,
        )
        return {
            "query": query,
            "bottom_up": [item.to_dict() for item in bottom_up],
            "top_down": {**top_down, "evidence": [item.to_dict() for item in top_down["evidence"]]},
            "graph_path": {**graph_path, "evidence": [item.to_dict() for item in graph_path["evidence"]]},
        }


def stable_run_id(query_bundle: Path) -> str:
    return hashlib.sha256(query_bundle.read_bytes()).hexdigest()[:12]
