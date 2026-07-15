"""Assemble a reviewer-ready, non-formal three-path evaluation candidate pack."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_regulatory_evidence_graph import normalize_alias


LEGACY = Path("data/eval/eval_queries_deepseek_v4_semantic_candidate_2026-07-10.json")
GAP_FILL = Path("data/eval/query_candidates_v2_gap_fill_2026-06-10.json")
TABLE = Path("data/eval/table_query_candidates_deepseek_v4_2026-07-10.json")
THREE_PATH = Path("data/eval/three_path_label_template_2026-07-11.json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def slice_for_gap_fill(row: dict[str, Any]) -> str:
    capabilities = " ".join(row.get("target_capability") or []).lower()
    if "table" in capabilities:
        return "table"
    if "cross_document" in capabilities:
        return "cross_document"
    if "scenario" in capabilities or "supply" in capabilities:
        return "supply_chain_evidence_path"
    return "document_structure"


def candidate_row(
    source_file: str,
    source_id: str,
    query: str,
    query_slice: str,
    candidate_chunks: list[str] | None = None,
    candidate_docs: list[str] | None = None,
    exclusion_reason: str = "",
) -> dict[str, Any]:
    return {
        "annotation_id": source_id,
        "query": query,
        "query_slice": query_slice,
        "candidate_evidence_chunk_ids": sorted(set(candidate_chunks or [])),
        "candidate_document_ids": sorted(set(candidate_docs or [])),
        "candidate_graph_path_node_ids": [],
        "gold_evidence_chunk_ids": [],
        "accepted_graph_path_node_ids": [],
        "review_status": "excluded" if exclusion_reason else "unreviewed",
        "eligible_for_formal_evaluation": False,
        "exclusion_reason": exclusion_reason,
        "sources": [{"file": source_file, "source_id": source_id}],
    }


def load_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_json(LEGACY):
        rows.append(candidate_row(
            str(LEGACY), str(row.get("query_id", "legacy")), str(row["query"]),
            "cross_document" if row.get("category") == "cross_document" else "single_clause",
            list(row.get("semantic_candidate_relevant_chunk_ids") or []),
            list(row.get("relevant_docs") or []),
        ))
    for row in read_json(GAP_FILL).get("candidates", []):
        rows.append(candidate_row(
            str(GAP_FILL), str(row.get("candidate_id", "gapfill")), str(row["query"]),
            slice_for_gap_fill(row), list(row.get("candidate_table_chunk_ids") or []),
            list(row.get("relevant_docs") or []),
        ))
    for row in read_json(TABLE).get("candidates", []):
        status = str(row.get("status", ""))
        exclusion = "no_viable_table_evidence_in_frozen_corpus" if status == "no_viable_table_evidence_in_frozen_corpus" else ""
        rows.append(candidate_row(
            str(TABLE), str(row.get("candidate_id", "table")), str(row["query"]), "table",
            list(row.get("candidate_table_chunk_ids") or []), list(row.get("relevant_docs") or []), exclusion,
        ))
    for row in read_json(THREE_PATH).get("queries", []):
        rows.append(candidate_row(
            str(THREE_PATH), str(row.get("query_id", "three_path")), str(row["query"]),
            str(row.get("query_slice", "")), [], [],
        ))
    return rows


def merge_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = normalize_alias(row["query"])
        if key not in merged:
            merged[key] = row
            continue
        current = merged[key]
        current["candidate_evidence_chunk_ids"] = sorted(set(current["candidate_evidence_chunk_ids"]) | set(row["candidate_evidence_chunk_ids"]))
        current["candidate_document_ids"] = sorted(set(current["candidate_document_ids"]) | set(row["candidate_document_ids"]))
        current["sources"].extend(row["sources"])
        if not current["exclusion_reason"]:
            current["review_status"] = row["review_status"] if row["review_status"] == "excluded" else current["review_status"]
            current["exclusion_reason"] = row["exclusion_reason"]
    return sorted(merged.values(), key=lambda row: (row["query_slice"], row["annotation_id"]))


def build_pack() -> dict[str, Any]:
    raw_rows = load_candidates()
    rows = merge_candidates(raw_rows)
    return {
        "schema_version": "1.0",
        "status": "candidate_pack_requires_human_review",
        "formal_metrics_ready": False,
        "counts": {
            "raw_source_records": len(raw_rows),
            "unique_queries": len(rows),
            "by_slice": dict(sorted(Counter(row["query_slice"] for row in rows).items())),
            "excluded": sum(row["review_status"] == "excluded" for row in rows),
        },
        "review_requirements": [
            "Confirm one or more source chunk IDs that directly support the answer.",
            "For graph questions, retain only factually valid and answer-relevant path nodes.",
            "Set eligible_for_formal_evaluation to true only after review_status is reviewed.",
        ],
        "queries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare three-path candidate annotation pack")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing annotation pack: {output}")
    pack = build_pack()
    output.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(pack["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
