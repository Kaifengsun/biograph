from __future__ import annotations

from pathlib import Path

from tools.relation_chain_ranking.common import chain_signature, nested_forbidden_keys
from tools.relation_chain_ranking.config import FORBIDDEN_INFERENCE_KEYS
from tools.relation_chain_ranking.core import (
    EdgeRecord,
    GraphData,
    build_node_aliases,
    candidate_features,
    detect_anchors,
    enumerate_candidates,
    method_scores,
)
from tools.relation_chain_ranking.evaluate import metric_row


def tiny_graph() -> GraphData:
    nodes = {
        "drug:a": {"id": "drug:a", "label": "Drug", "name": "Alpha Drug", "properties": {}},
        "api:a": {"id": "api:a", "label": "API", "name": "Alpha API", "properties": {}},
        "mfg:x": {"id": "mfg:x", "label": "Manufacturer", "name": "Maker X", "properties": {}},
        "mfg:y": {"id": "mfg:y", "label": "Manufacturer", "name": "Maker Y", "properties": {}},
    }
    edge_keys = [
        ("drug:a", "CONTAINS_API", "api:a"),
        ("api:a", "SUPPLIED_BY", "mfg:x"),
        ("api:a", "SUPPLIED_BY", "mfg:y"),
        ("drug:a", "APPLIES_DEFINITION_FROM", "api:a"),
    ]
    edges = {key: EdgeRecord(*key, ("p",)) for key in edge_keys}
    adjacency = {}
    for node_id in nodes:
        adjacency[node_id] = tuple(
            sorted(
                [key for key in edge_keys if node_id in (key[0], key[2])],
                key=lambda x: (x[1], x[0], x[2]),
            )
        )
    node_aliases, alias_index = build_node_aliases(nodes)
    return GraphData(nodes, edges, adjacency, node_aliases, alias_index)


def test_inference_forbidden_keys_are_detected_recursively() -> None:
    payload = {"queries": [{"review_id": "Q1", "final_question": "x", "gold_edges": []}]}
    assert nested_forbidden_keys(payload, FORBIDDEN_INFERENCE_KEYS) == ["$.queries[0].gold_edges"]


def test_anchor_detection_keeps_longest_alias_and_colliding_nodes() -> None:
    graph = tiny_graph()
    graph.nodes["chunk:shadow"] = {
        "id": "chunk:shadow",
        "label": "DocChunk",
        "name": "Alpha Drug",
        "properties": {},
    }
    node_aliases, alias_index = build_node_aliases(graph.nodes)
    graph.node_aliases = node_aliases
    graph.alias_index = alias_index
    anchors = detect_anchors("Which API is linked to Alpha Drug?", graph)
    assert anchors[0]["node_id"] == "drug:a"
    assert anchors[0]["alias"] == "alpha drug"
    assert "chunk:shadow" not in {row["node_id"] for row in anchors}


def test_enumeration_supports_branching_and_parallel_semantic_edges() -> None:
    graph = tiny_graph()
    result = enumerate_candidates("Which API and suppliers are linked to Alpha Drug?", graph)
    branching = chain_signature(
        [
            ("drug:a", "CONTAINS_API", "api:a"),
            ("api:a", "SUPPLIED_BY", "mfg:x"),
            ("api:a", "SUPPLIED_BY", "mfg:y"),
        ]
    )
    parallel = chain_signature(
        [
            ("drug:a", "CONTAINS_API", "api:a"),
            ("drug:a", "APPLIES_DEFINITION_FROM", "api:a"),
        ]
    )
    signatures = {candidate.signature for candidate in result.candidates}
    assert branching in signatures
    assert parallel in signatures
    assert not result.work_limit_aborted


def test_matched_ablation_scores_remove_only_declared_terms() -> None:
    graph = tiny_graph()
    result = enumerate_candidates("Which API and suppliers are linked to Alpha Drug?", graph)
    target = next(
        candidate
        for candidate in result.candidates
        if len(candidate.edges) == 3
        and {edge[1] for edge in candidate.edges} == {"CONTAINS_API", "SUPPLIED_BY"}
    )
    features = candidate_features("Which API and suppliers are linked to Alpha Drug?", target, graph)
    scores = method_scores(features)
    assert scores["r1"] >= scores["direction_off"] >= scores["m0"]
    assert scores["r1"] >= scores["cue_off"]
    assert scores["m0"] == features["core"]


def test_hit_at_k_with_short_ranking_is_standard() -> None:
    row = metric_row(["gold"], "gold")
    assert row["hit_at_1"] == 1.0
    assert row["hit_at_3"] == 1.0
    assert row["hit_at_5"] == 1.0
    assert row["mrr"] == 1.0


def test_missing_gold_has_zero_metrics() -> None:
    row = metric_row(["a", "b"], "gold")
    assert row["rank"] is None
    assert row["hit_at_5"] == 0.0
    assert row["mrr"] == 0.0


def test_eu_gmp_annex_alias_repairs_internal_ema_identifier() -> None:
    nodes = {
        "regdoc:ema_gmp_annex_11": {
            "id": "regdoc:ema_gmp_annex_11",
            "label": "RegulatoryDocument",
            "name": "EudraLex",
            "properties": {"doc_id": "ema_gmp_annex_11"},
        },
        "topic:x": {"id": "topic:x", "label": "Topic", "name": "Systems", "properties": {}},
    }
    key = ("regdoc:ema_gmp_annex_11", "COVERS_TOPIC", "topic:x")
    edges = {key: EdgeRecord(*key, ("p",))}
    node_aliases, alias_index = build_node_aliases(nodes)
    graph = GraphData(
        nodes,
        edges,
        {"regdoc:ema_gmp_annex_11": (key,), "topic:x": (key,)},
        node_aliases,
        alias_index,
    )
    anchors = detect_anchors("What does EU GMP Annex 11 cover?", graph)
    assert [row["node_id"] for row in anchors] == ["regdoc:ema_gmp_annex_11"]
