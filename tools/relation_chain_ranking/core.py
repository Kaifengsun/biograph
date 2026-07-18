from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .common import chain_signature, normalized_phrase, normalized_tokens
from .config import (
    ALIAS_PROPERTY_ALLOWLIST,
    ANCHOR_ALIAS_EQUIVALENCES,
    MAX_ANCHORS,
    MAX_CANDIDATES,
    MAX_EDGE_ATTEMPTS,
    MAX_EDGES,
    PROJECTED_RELATIONS,
    RELATION_ALIASES,
    STOP_WORDS,
    WEIGHTS,
)


EdgeKey = tuple[str, str, str]


@dataclass(frozen=True)
class EdgeRecord:
    source: str
    relation: str
    target: str
    provenance_hashes: tuple[str, ...]

    @property
    def key(self) -> EdgeKey:
        return self.source, self.relation, self.target

    @property
    def has_provenance(self) -> bool:
        return bool(self.provenance_hashes)


@dataclass
class GraphData:
    nodes: dict[str, dict[str, Any]]
    edges: dict[EdgeKey, EdgeRecord]
    adjacency: dict[str, tuple[EdgeKey, ...]]
    node_aliases: dict[str, tuple[tuple[str, ...], ...]]
    alias_index: dict[tuple[str, ...], tuple[str, ...]]


@dataclass
class Candidate:
    signature: str
    edges: tuple[EdgeKey, ...]
    nodes: tuple[str, ...]
    provenance_fraction: float
    orientation: float
    anchors: set[str] = field(default_factory=set)


@dataclass
class EnumerationResult:
    candidates: list[Candidate]
    anchors: list[dict[str, Any]]
    attempted_edge_additions: int
    candidate_cap_reached: bool
    work_limit_aborted: bool
    per_anchor_emitted: dict[str, int]


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _node_alias_values(node: dict[str, Any]) -> Iterable[Any]:
    yield node.get("name", "")
    node_id = str(node.get("id", ""))
    if ":" in node_id:
        yield node_id.split(":", 1)[1]
    props = node.get("properties", {})
    for key in ALIAS_PROPERTY_ALLOWLIST:
        yield props.get(key, "")


def build_node_aliases(nodes: dict[str, dict[str, Any]]) -> tuple[
    dict[str, tuple[tuple[str, ...], ...]], dict[tuple[str, ...], tuple[str, ...]]
]:
    node_aliases: dict[str, tuple[tuple[str, ...], ...]] = {}
    alias_nodes: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for node_id, node in nodes.items():
        aliases = set()
        for value in _node_alias_values(node):
            tokens = normalized_tokens(value)
            if len("".join(tokens)) >= 3:
                aliases.add(tokens)
                phrase = " ".join(tokens)
                for equivalent in ANCHOR_ALIAS_EQUIVALENCES.get(phrase, ()):
                    aliases.add(normalized_tokens(equivalent))
        ordered = tuple(sorted(aliases, key=lambda x: (-len(x), -sum(map(len, x)), x)))
        node_aliases[node_id] = ordered
        for alias in ordered:
            alias_nodes[alias].add(node_id)
    alias_index = {alias: tuple(sorted(ids)) for alias, ids in alias_nodes.items()}
    return node_aliases, alias_index


def load_graph(nodes_path: Path, edges_path: Path) -> GraphData:
    nodes: dict[str, dict[str, Any]] = {}
    with nodes_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            node_id = str(row["id"])
            if node_id in nodes:
                raise ValueError(f"duplicate node ID: {node_id}")
            nodes[node_id] = row

    grouped: dict[EdgeKey, set[str]] = defaultdict(set)
    with edges_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            relation = str(row["relation"])
            if relation not in PROJECTED_RELATIONS:
                continue
            key = str(row["source"]), relation, str(row["target"])
            if key[0] not in nodes or key[2] not in nodes:
                raise ValueError(f"edge references missing node: {key}")
            grouped.setdefault(key, set())
            provenance = row.get("properties", {}).get("provenance")
            if provenance:
                grouped[key].add(_json_hash(provenance))
    edges = {
        key: EdgeRecord(*key, tuple(sorted(provenance_hashes)))
        for key, provenance_hashes in grouped.items()
    }
    adjacency_lists: dict[str, list[EdgeKey]] = defaultdict(list)
    for key in edges:
        adjacency_lists[key[0]].append(key)
        adjacency_lists[key[2]].append(key)
    adjacency = {
        node_id: tuple(sorted(keys, key=lambda x: (x[1], x[0], x[2])))
        for node_id, keys in adjacency_lists.items()
    }
    node_aliases, alias_index = build_node_aliases(nodes)
    return GraphData(nodes, edges, adjacency, node_aliases, alias_index)


def detect_anchors(question: str, graph: GraphData) -> list[dict[str, Any]]:
    question_tokens = normalized_tokens(question)
    matches: list[tuple[int, int, tuple[str, ...]]] = []
    for alias in graph.alias_index:
        width = len(alias)
        if not width or width > len(question_tokens):
            continue
        for start in range(len(question_tokens) - width + 1):
            if question_tokens[start : start + width] == alias:
                matches.append((start, start + width, alias))
    matches.sort(key=lambda x: (-(x[1] - x[0]), -sum(map(len, x[2])), x[0], x[2]))
    selected: list[tuple[int, int, tuple[str, ...]]] = []
    occupied: set[int] = set()
    for match in matches:
        positions = set(range(match[0], match[1]))
        if positions & occupied:
            continue
        selected.append(match)
        occupied.update(positions)

    anchors = []
    for start, end, alias in selected:
        for node_id in graph.alias_index[alias]:
            anchors.append(
                {
                    "node_id": node_id,
                    "alias": " ".join(alias),
                    "span": [start, end],
                    "alias_token_count": len(alias),
                    "alias_char_count": sum(map(len, alias)),
                }
            )
    anchors.sort(
        key=lambda row: (
            -row["alias_token_count"],
            -row["alias_char_count"],
            row["node_id"],
            row["span"],
        )
    )
    unique = []
    seen = set()
    for row in anchors:
        key = row["node_id"]
        if key not in seen and graph.adjacency.get(key):
            seen.add(key)
            unique.append(row)
    return unique[:MAX_ANCHORS]


def _existing_pairs(edges: tuple[EdgeKey, ...]) -> set[frozenset[str]]:
    return {frozenset((source, target)) for source, _, target in edges}


def _would_close_nonparallel_cycle(
    state_edges: tuple[EdgeKey, ...],
    state_nodes: frozenset[str],
    edge: EdgeKey,
) -> bool:
    source, _, target = edge
    if source not in state_nodes or target not in state_nodes:
        return False
    return frozenset((source, target)) not in _existing_pairs(state_edges)


def enumerate_candidates(question: str, graph: GraphData) -> EnumerationResult:
    anchors = detect_anchors(question, graph)
    queues: list[deque[tuple[tuple[EdgeKey, ...], frozenset[str], dict[str, int], float]]] = []
    anchor_ids = []
    for row in anchors:
        node_id = row["node_id"]
        anchor_ids.append(node_id)
        queues.append(deque([(tuple(), frozenset({node_id}), {node_id: 0}, 0.0)]))
    best_state_orientation: dict[str, float] = {}
    candidates: dict[str, Candidate] = {}
    per_anchor = CounterLike()
    attempts = 0
    aborted = False
    cap_reached = False

    while queues and any(queues):
        for index, queue in enumerate(queues):
            if not queue:
                continue
            state_edges, state_nodes, depths, forward_sum = queue.popleft()
            incident = sorted(
                {key for node_id in state_nodes for key in graph.adjacency.get(node_id, ())},
                key=lambda x: (x[1], x[0], x[2]),
            )
            for edge in incident:
                attempts += 1
                if attempts > MAX_EDGE_ATTEMPTS:
                    aborted = True
                    break
                if edge in state_edges or _would_close_nonparallel_cycle(state_edges, state_nodes, edge):
                    continue
                source, _, target = edge
                if source not in state_nodes and target not in state_nodes:
                    continue
                next_edges = tuple(sorted((*state_edges, edge)))
                if len(next_edges) > MAX_EDGES:
                    continue
                next_nodes = frozenset((*state_nodes, source, target))
                next_depths = dict(depths)
                if source in state_nodes and target not in state_nodes:
                    next_depths[target] = min(depths[source] + 1, next_depths.get(target, 10**9))
                    forward = 1.0
                elif target in state_nodes and source not in state_nodes:
                    next_depths[source] = min(depths[target] + 1, next_depths.get(source, 10**9))
                    forward = 0.0
                else:
                    forward = float(depths.get(source, 10**9) <= depths.get(target, 10**9))
                next_forward = forward_sum + forward
                signature = chain_signature(next_edges)
                orientation = 2.0 * (next_forward / len(next_edges)) - 1.0
                provenance_fraction = sum(graph.edges[key].has_provenance for key in next_edges) / len(next_edges)
                candidate = candidates.get(signature)
                if candidate is None:
                    candidates[signature] = Candidate(
                        signature=signature,
                        edges=next_edges,
                        nodes=tuple(sorted(next_nodes)),
                        provenance_fraction=provenance_fraction,
                        orientation=orientation,
                        anchors={anchor_ids[index]},
                    )
                    per_anchor.increment(anchor_ids[index])
                    if len(candidates) >= MAX_CANDIDATES:
                        cap_reached = True
                        break
                else:
                    candidate.orientation = max(candidate.orientation, orientation)
                    candidate.anchors.add(anchor_ids[index])
                previous_orientation = best_state_orientation.get(signature, -2.0)
                if orientation > previous_orientation + 1e-12:
                    best_state_orientation[signature] = orientation
                    if len(next_edges) < MAX_EDGES:
                        queue.append((next_edges, next_nodes, next_depths, next_forward))
            if aborted or cap_reached:
                break
        if aborted or cap_reached:
            break
    if aborted:
        candidates = {}
    return EnumerationResult(
        candidates=sorted(candidates.values(), key=lambda row: (len(row.edges), row.signature)),
        anchors=anchors,
        attempted_edge_additions=attempts,
        candidate_cap_reached=cap_reached,
        work_limit_aborted=aborted,
        per_anchor_emitted=dict(sorted(per_anchor.values.items())),
    )


class CounterLike:
    def __init__(self) -> None:
        self.values: dict[str, int] = defaultdict(int)

    def increment(self, key: str) -> None:
        self.values[key] += 1


def relation_cues(question: str) -> set[str]:
    tokens = normalized_tokens(question)
    matches: list[tuple[int, int, str]] = []
    for relation, aliases in RELATION_ALIASES.items():
        for alias_text in aliases:
            alias = normalized_tokens(alias_text)
            for start in range(len(tokens) - len(alias) + 1):
                if tokens[start : start + len(alias)] == alias:
                    matches.append((start, start + len(alias), relation))
    matches.sort(key=lambda x: (-(x[1] - x[0]), x[0], x[2]))
    selected = []
    occupied: set[int] = set()
    for match in matches:
        positions = set(range(match[0], match[1]))
        if positions & occupied:
            continue
        selected.append(match)
        occupied.update(positions)
    return {relation for _, _, relation in selected}


def _set_f1(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if not overlap:
        return 0.0
    precision = overlap / len(right)
    recall = overlap / len(left)
    return 2.0 * precision * recall / (precision + recall)


def candidate_features(question: str, candidate: Candidate, graph: GraphData) -> dict[str, float | list[str]]:
    question_set = set(normalized_tokens(question)) - STOP_WORDS
    node_tokens = {
        token
        for node_id in candidate.nodes
        for alias in graph.node_aliases.get(node_id, ())
        for token in alias
        if token not in STOP_WORDS
    }
    cues = relation_cues(question)
    relation_list = [edge[1] for edge in candidate.edges]
    relation_set = set(relation_list)
    coverage = len(cues & relation_set) / len(cues) if cues else 0.0
    precision = sum(relation in cues for relation in relation_list) / len(relation_list) if cues else 0.0
    token_f1 = _set_f1(question_set, node_tokens)
    core = (
        WEIGHTS["node_token_f1"] * token_f1
        + WEIGHTS["provenance"] * candidate.provenance_fraction
        + WEIGHTS["extra_edge"] * (len(candidate.edges) - 1)
    )
    return {
        "node_token_f1": token_f1,
        "provenance_fraction": candidate.provenance_fraction,
        "edge_count": float(len(candidate.edges)),
        "relation_coverage": coverage,
        "relation_precision": precision,
        "orientation": candidate.orientation,
        "relation_cues": sorted(cues),
        "core": core,
    }


def method_scores(features: dict[str, Any]) -> dict[str, float]:
    core = float(features["core"])
    coverage = float(features["relation_coverage"])
    precision = float(features["relation_precision"])
    orientation = float(features["orientation"])
    relation_term = WEIGHTS["relation_coverage"] * coverage + WEIGHTS["relation_precision"] * precision
    orientation_term = WEIGHTS["orientation"] * orientation
    return {
        "m0": core,
        "cue_off": core + orientation_term,
        "direction_off": core + relation_term,
        "r1": core + relation_term + orientation_term,
    }
