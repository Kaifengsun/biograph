"""Attach generated hierarchy summaries to a new immutable graph snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def summary_node_id(summary_id: str) -> str:
    return f"summary:{summary_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach hierarchy summary nodes to graph snapshot")
    parser.add_argument("--graph", required=True)
    parser.add_argument("--summary-input", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    graph = Path(args.graph)
    summary_input = Path(args.summary_input)
    summary_output = Path(args.summary_output)
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing graph snapshot: {output}")

    nodes = read_jsonl(graph / "nodes.jsonl")
    edges = read_jsonl(graph / "edges.jsonl")
    plans = {row["summary_id"]: row for row in read_jsonl(summary_input / "hierarchy_summary_inputs.jsonl")}
    summaries = read_jsonl(summary_output / "hierarchy_summaries.jsonl")
    if set(plans) != {row["summary_id"] for row in summaries}:
        raise RuntimeError("summary input/output IDs do not match")

    for summary in summaries:
        plan = plans[summary["summary_id"]]
        node_id = summary_node_id(summary["summary_id"])
        is_document = summary["summary_type"] == "document"
        nodes.append({
            "id": node_id,
            "label": "DocumentSummary" if is_document else "SectionSummary",
            "name": summary["heading"],
            "properties": {
                "summary_id": summary["summary_id"],
                "doc_id": summary["doc_id"],
                "summary": summary["summary"],
                "retrieval_eligible": summary["summary"] != "[INSUFFICIENT_SOURCE]",
                "model": summary["model"],
                "prompt_version": summary["prompt_version"],
                "omitted_source_ids": summary["omitted_source_ids"],
                "provenance": {
                    "graph_version": "regulatory-evidence-graph-v1-hierarchy",
                    "source_file": str(summary_output / "hierarchy_summaries.jsonl"),
                    "source_locator": summary["summary_id"],
                    "derivation": "source_grounded_hierarchy_aggregation",
                },
            },
        })
        target = plan["target_node_id"]
        edges.append({
            "source": target,
            "target": node_id,
            "relation": "HAS_DOCUMENT_SUMMARY" if is_document else "HAS_SECTION_SUMMARY",
            "properties": {"provenance": {"derivation": "hierarchy_summary_attachment"}},
        })
        for unit in plan["source_units"]:
            dependency = unit.get("depends_on")
            source = summary_node_id(dependency) if dependency else f"chunk:{unit['source_id']}"
            edges.append({
                "source": node_id,
                "target": source,
                "relation": "SUMMARIZES",
                "properties": {
                    "source_type": unit["source_type"],
                    "provenance": {"derivation": "hierarchy_summary_input"},
                },
            })

    node_map = {node["id"]: node for node in nodes}
    edge_map = {(edge["source"], edge["target"], edge["relation"]): edge for edge in edges}
    output.mkdir(parents=True)
    write_jsonl(output / "nodes.jsonl", sorted(node_map.values(), key=lambda node: node["id"]))
    write_jsonl(output / "edges.jsonl", sorted(edge_map.values(), key=lambda edge: (edge["relation"], edge["source"], edge["target"])))
    base_manifest = json.loads((graph / "graph_manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "graph_version": "regulatory-evidence-graph-v1-hierarchy",
        "base_graph": str(graph),
        "summary_input": str(summary_input),
        "summary_output": str(summary_output),
        "base_counts": base_manifest["counts"],
        "added_section_summaries": sum(row["summary_type"] == "section" for row in summaries),
        "added_document_summaries": sum(row["summary_type"] == "document" for row in summaries),
        "nodes": len(node_map),
        "edges": len(edge_map),
        "canonical_artifacts_replaced": False,
    }
    write_json(output / "graph_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
