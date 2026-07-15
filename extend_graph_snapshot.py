"""Create a new graph snapshot by attaching validated JSONL graph artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from build_regulatory_evidence_graph import dedupe_edges, read_jsonl, write_json, write_jsonl


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repair_known_drug_area_map_endpoints(nodes: dict[str, dict[str, Any]], edges: Iterable[dict[str, Any]]) -> list[str]:
    """Materialize legacy DrugClass endpoints from the authoritative local map."""
    from pharma_supply_chain import core_data

    known_classes = {str(drug_id) for drug_id, _area_id in getattr(core_data, "DRUG_AREA_MAP", {}).items()}
    required_sources = {
        edge["source"].removeprefix("entity:")
        for edge in edges
        if edge.get("relation") == "BELONGS_TO_AREA" and edge.get("source", "").startswith("entity:")
    }
    repaired = []
    for class_id in sorted(known_classes & required_sources):
        node_id = f"entity:{class_id}"
        if node_id in nodes:
            continue
        nodes[node_id] = {
            "id": node_id,
            "label": "DrugClass",
            "name": class_id.replace("_", " "),
            "properties": {
                "class_id": class_id,
                "provenance": {
                    "source_file": "pharma_supply_chain/core_data.py",
                    "source_locator": "DRUG_AREA_MAP",
                    "derivation": "legacy_graph_endpoint_repair_from_structured_map",
                },
            },
        }
        repaired.append(node_id)
    return repaired


def extend_snapshot(
    base: Path,
    output: Path,
    extra_node_files: Iterable[Path],
    extra_edge_files: Iterable[Path],
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing graph snapshot: {output}")
    base_nodes = read_jsonl(base / "nodes.jsonl")
    base_edges = read_jsonl(base / "edges.jsonl")
    nodes = {node["id"]: node for node in base_nodes}
    edges = list(base_edges)
    attachment_hashes: dict[str, str] = {}

    for path in extra_node_files:
        attachment_hashes[str(path)] = sha256_file(path)
        for node in read_jsonl(path):
            existing = nodes.get(node["id"])
            if existing is not None and existing != node:
                raise ValueError(f"conflicting node ID in attachment: {node['id']}")
            nodes[node["id"]] = node
    for path in extra_edge_files:
        attachment_hashes[str(path)] = sha256_file(path)
        edges.extend(read_jsonl(path))

    repaired_endpoints = repair_known_drug_area_map_endpoints(nodes, edges)
    unique_edges = dedupe_edges(edges)
    dangling_edges = [edge for edge in unique_edges if edge["source"] not in nodes or edge["target"] not in nodes]
    if dangling_edges:
        raise ValueError(f"graph extension contains {len(dangling_edges)} dangling edges")
    output.mkdir(parents=True)
    write_jsonl(output / "nodes.jsonl", sorted(nodes.values(), key=lambda row: row["id"]))
    write_jsonl(output / "edges.jsonl", unique_edges)
    report = {
        "base_snapshot": str(base),
        "base_nodes_sha256": sha256_file(base / "nodes.jsonl"),
        "base_edges_sha256": sha256_file(base / "edges.jsonl"),
        "attachments": attachment_hashes,
        "integrity_repairs": {
            "materialized_drug_class_nodes": repaired_endpoints,
            "count": len(repaired_endpoints),
        },
        "counts": {
            "nodes": len(nodes),
            "edges": len(unique_edges),
            "relations": dict(sorted(Counter(edge["relation"] for edge in unique_edges).items())),
        },
        "canonical_artifacts_replaced": False,
    }
    write_json(output / "graph_extension_manifest.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend a staged graph snapshot with validated JSONL artifacts")
    parser.add_argument("--base", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--extra-nodes", action="append", required=True)
    parser.add_argument("--extra-edges", action="append", required=True)
    args = parser.parse_args()
    report = extend_snapshot(
        Path(args.base),
        Path(args.output),
        [Path(path) for path in args.extra_nodes],
        [Path(path) for path in args.extra_edges],
    )
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
