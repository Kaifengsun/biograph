"""Prepare bottom-up, provenance-preserving inputs for hierarchy summaries.

No LLM calls occur here. Records reference leaf chunk evidence or lower-level
section summaries so a later generator can run in dependency order.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_GRAPH = Path("artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build1")
DEFAULT_SOURCE = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
MAX_SECTION_CHARS = 18_000
MAX_DOCUMENT_CHARS = 30_000


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def chunk_source_text(node: dict[str, Any], content_by_chunk: dict[str, str]) -> str:
    props = node["properties"]
    summary = str(props.get("summary") or "").strip()
    if summary:
        return summary
    content = content_by_chunk.get(str(props["chunk_id"]), "").strip()
    heading = str(props.get("heading") or "").strip()
    return "\n".join(part for part in (heading, content) if part)


def select_units(units: list[dict[str, Any]], max_chars: int) -> tuple[list[dict[str, Any]], list[str]]:
    selected: list[dict[str, Any]] = []
    omitted: list[str] = []
    used = 0
    for unit in units:
        text = str(unit.get("source_text") or "")
        if used + len(text) <= max_chars:
            selected.append(unit)
            used += len(text)
        else:
            omitted.append(str(unit["source_id"]))
    return selected, omitted


def build_inputs(graph_dir: Path, source_dir: Path, output: Path) -> dict[str, Any]:
    nodes = read_jsonl(graph_dir / "nodes.jsonl")
    edges = read_jsonl(graph_dir / "edges.jsonl")
    chunk_nodes = {node["id"]: node for node in nodes if node["label"] == "DocChunk"}
    document_nodes = {node["id"]: node for node in nodes if node["label"] == "RegulatoryDocument"}

    content_by_chunk: dict[str, str] = {}
    for path in source_dir.glob("*_enriched.json"):
        for row in read_json(path):
            content_by_chunk[str(row["chunk_id"])] = str(row.get("content") or "")

    children: dict[str, list[str]] = defaultdict(list)
    roots: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["relation"] == "PARENT_OF":
            children[edge["source"]].append(edge["target"])
        elif edge["relation"] == "CONTAINS" and edge["target"] in chunk_nodes:
            roots[edge["source"]].append(edge["target"])

    section_ids = {parent for parent, child_ids in children.items() if child_ids}
    records: list[dict[str, Any]] = []
    for parent in section_ids:
        node = chunk_nodes[parent]
        props = node["properties"]
        units: list[dict[str, Any]] = [{
            "source_id": props["chunk_id"],
            "source_type": "section_header_chunk",
            "heading": props.get("heading", ""),
            "source_text": chunk_source_text(node, content_by_chunk),
        }]
        for child in children[parent]:
            child_node = chunk_nodes[child]
            child_props = child_node["properties"]
            units.append({
                "source_id": child_props["chunk_id"],
                "source_type": "section_summary" if child in section_ids else "leaf_chunk",
                "heading": child_props.get("heading", ""),
                "source_text": "" if child in section_ids else chunk_source_text(child_node, content_by_chunk),
                "depends_on": f"section:{child_props['chunk_id']}" if child in section_ids else None,
            })
        units, omitted = select_units(units, MAX_SECTION_CHARS)
        records.append({
            "summary_id": f"section:{props['chunk_id']}",
            "summary_type": "section",
            "target_node_id": parent,
            "doc_id": props["doc_id"],
            "heading": props.get("heading", ""),
            "level": props.get("level", 0),
            "source_units": units,
            "omitted_source_ids": omitted,
            "max_input_chars": MAX_SECTION_CHARS,
            "provenance": {
                "graph_snapshot": str(graph_dir),
                "derivation": "direct_parent_child_edges",
            },
        })

    for doc_node_id, root_ids in roots.items():
        doc_node = document_nodes[doc_node_id]
        doc_id = doc_node["properties"]["doc_id"]
        units: list[dict[str, Any]] = []
        for root in root_ids:
            root_node = chunk_nodes[root]
            root_props = root_node["properties"]
            units.append({
                "source_id": root_props["chunk_id"],
                "source_type": "section_summary" if root in section_ids else "root_chunk",
                "heading": root_props.get("heading", ""),
                "source_text": "" if root in section_ids else chunk_source_text(root_node, content_by_chunk),
                "depends_on": f"section:{root_props['chunk_id']}" if root in section_ids else None,
            })
        units, omitted = select_units(units, MAX_DOCUMENT_CHARS)
        records.append({
            "summary_id": f"document:{doc_id}",
            "summary_type": "document",
            "target_node_id": doc_node_id,
            "doc_id": doc_id,
            "heading": doc_node["name"],
            "level": 0,
            "source_units": units,
            "omitted_source_ids": omitted,
            "max_input_chars": MAX_DOCUMENT_CHARS,
            "provenance": {
                "graph_snapshot": str(graph_dir),
                "derivation": "document_root_edges",
            },
        })

    records.sort(key=lambda row: (row["summary_type"] == "document", -int(row["level"]), row["summary_id"]))
    output.mkdir(parents=True, exist_ok=False)
    write_jsonl(output / "hierarchy_summary_inputs.jsonl", records)
    report = {
        "status": "prepared_no_llm_calls",
        "graph_snapshot": str(graph_dir),
        "source_corpus": str(source_dir),
        "section_summary_inputs": sum(row["summary_type"] == "section" for row in records),
        "document_summary_inputs": sum(row["summary_type"] == "document" for row in records),
        "total_records": len(records),
        "records_with_omitted_sources": sum(bool(row["omitted_source_ids"]) for row in records),
        "max_section_chars": MAX_SECTION_CHARS,
        "max_document_chars": MAX_DOCUMENT_CHARS,
        "expected_llm_calls": len(records),
        "paid_api_calls": 0,
    }
    write_json(output / "hierarchy_summary_input_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare hierarchy summary inputs without LLM calls")
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH))
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output}")
    report = build_inputs(Path(args.graph), Path(args.source), output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
