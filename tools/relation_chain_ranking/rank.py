from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from .common import nested_forbidden_keys, read_json, sha256_file, write_json
from .config import (
    ALIAS_PROPERTY_ALLOWLIST,
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    FORBIDDEN_INFERENCE_KEYS,
    MAX_ANCHORS,
    MAX_CANDIDATES,
    MAX_EDGE_ATTEMPTS,
    MAX_EDGES,
    METHODS,
    PROJECTED_RELATIONS,
    RELATION_ALIASES,
    STOP_WORDS,
    WEIGHTS,
)
from .core import candidate_features, enumerate_candidates, load_graph, method_scores


ROOT = Path(__file__).resolve().parents[2]


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def build_lock(nodes: Path, edges: Path, inference: Path) -> dict[str, Any]:
    config_path = Path(__file__).with_name("config.py")
    spec_path = ROOT / "docs/superpowers/specs/2026-07-18-relation-aware-graph-path-ranking-design.md"
    return {
        "schema_version": "1.0",
        "status": "locked_before_graph_chain_scores",
        "experiment_classification": "feedback_driven_exploratory_supplementary",
        "git_commit": git_commit(),
        "input_hashes": {
            "nodes": sha256_file(nodes),
            "edges": sha256_file(edges),
            "inference_queries": sha256_file(inference),
            "config_py": sha256_file(config_path),
            "approved_spec": sha256_file(spec_path),
        },
        "projection_relations": list(PROJECTED_RELATIONS),
        "alias_property_allowlist": list(ALIAS_PROPERTY_ALLOWLIST),
        "relation_aliases": {key: list(value) for key, value in RELATION_ALIASES.items()},
        "stop_words": sorted(STOP_WORDS),
        "weights": WEIGHTS,
        "methods": list(METHODS),
        "limits": {
            "max_anchors": MAX_ANCHORS,
            "max_edges": MAX_EDGES,
            "max_candidates": MAX_CANDIDATES,
            "max_edge_attempts": MAX_EDGE_ATTEMPTS,
        },
        "bootstrap": {"iterations": BOOTSTRAP_ITERATIONS, "seed": BOOTSTRAP_SEED},
        "candidate_identity": "sorted set of canonical (source, relation, target) triples",
        "tie_breaking": {
            "b0": ["edge_count_asc", "signature_asc"],
            "scored": ["score_desc", "edge_count_asc", "signature_asc"],
        },
    }


def validate_lock(lock: dict[str, Any], nodes: Path, edges: Path, inference: Path) -> None:
    expected = build_lock(nodes, edges, inference)
    comparable_keys = [
        "input_hashes",
        "projection_relations",
        "alias_property_allowlist",
        "relation_aliases",
        "stop_words",
        "weights",
        "methods",
        "limits",
        "bootstrap",
        "candidate_identity",
        "tie_breaking",
    ]
    mismatches = [key for key in comparable_keys if lock.get(key) != expected.get(key)]
    if mismatches:
        raise ValueError(f"method lock mismatch: {mismatches}")


def rank_variant(question: str, graph: Any) -> dict[str, Any]:
    enumeration = enumerate_candidates(question, graph)
    candidate_rows = []
    for candidate in enumeration.candidates:
        features = candidate_features(question, candidate, graph)
        scores = method_scores(features)
        candidate_rows.append(
            {
                "signature": candidate.signature,
                "edges": [list(edge) for edge in candidate.edges],
                "anchors": sorted(candidate.anchors),
                "features": features,
                "scores": scores,
            }
        )
    rankings: dict[str, list[str]] = {
        "b0": [row["signature"] for row in candidate_rows],
    }
    for method in METHODS:
        if method == "b0":
            continue
        rankings[method] = [
            row["signature"]
            for row in sorted(
                candidate_rows,
                key=lambda row: (
                    -float(row["scores"][method]),
                    len(row["edges"]),
                    row["signature"],
                ),
            )
        ]
    return {
        "question": question,
        "anchor_matches": enumeration.anchors,
        "candidate_count": len(candidate_rows),
        "attempted_edge_additions": enumeration.attempted_edge_additions,
        "candidate_cap_reached": enumeration.candidate_cap_reached,
        "work_limit_aborted": enumeration.work_limit_aborted,
        "per_anchor_emitted": enumeration.per_anchor_emitted,
        "candidates": candidate_rows,
        "rankings": rankings,
    }


def run_inference(
    nodes: Path,
    edges: Path,
    inference_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    inference = read_json(inference_path)
    forbidden = nested_forbidden_keys(inference, FORBIDDEN_INFERENCE_KEYS)
    if forbidden:
        raise ValueError(f"inference input contains forbidden keys: {forbidden}")
    if inference.get("query_count") != 30 or len(inference.get("queries", [])) != 30:
        raise ValueError("expected exactly 30 sanitized inference queries")
    lock = read_json(lock_path)
    validate_lock(lock, nodes, edges, inference_path)
    graph = load_graph(nodes, edges)
    rows = []
    for index, query in enumerate(inference["queries"], 1):
        print(f"[{index:02d}/30] {query['review_id']} final", flush=True)
        variants = {"final": rank_variant(query["final_question"], graph)}
        if query["wording_changed"]:
            print(f"         {query['review_id']} original sensitivity", flush=True)
            variants["original"] = rank_variant(query["original_question"], graph)
        rows.append(
            {
                "review_id": query["review_id"],
                "category": query["category"],
                "wording_changed": query["wording_changed"],
                "variants": variants,
            }
        )
    return {
        "schema_version": "1.0",
        "status": "rankings_serialized_before_gold_join",
        "experiment_classification": lock["experiment_classification"],
        "method_lock_sha256": sha256_file(lock_path),
        "query_count": len(rows),
        "queries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock_parser = subparsers.add_parser("lock")
    run_parser = subparsers.add_parser("run")
    for child in (lock_parser, run_parser):
        child.add_argument("--nodes", type=Path, required=True)
        child.add_argument("--edges", type=Path, required=True)
        child.add_argument("--inference", type=Path, required=True)
    lock_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--lock", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "lock":
        payload = build_lock(args.nodes, args.edges, args.inference)
        write_json(args.output, payload)
        print(f"method locked at {args.output}")
        return
    payload = run_inference(args.nodes, args.edges, args.inference, args.lock)
    write_json(args.output, payload)
    print(f"serialized rankings at {args.output}")


if __name__ == "__main__":
    main()
