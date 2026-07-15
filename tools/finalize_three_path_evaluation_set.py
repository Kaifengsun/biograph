"""Finalize the audited 60-query three-path evaluation set without mutating reviews."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from freeze_three_path_evaluation_set import freeze_pack


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_chunk_ids(corpus: Path) -> set[str]:
    ids: set[str] = set()
    for path in corpus.glob("*_enriched.json"):
        for row in read_json(path):
            chunk_id = str(row.get("chunk_id", ""))
            if chunk_id:
                ids.add(chunk_id)
    return ids


def graph_node_ids(graph: Path) -> set[str]:
    return {str(row["id"]) for row in (json.loads(line) for line in (graph / "nodes.jsonl").read_text(encoding="utf-8").splitlines())}


def finalize(provisional: dict[str, Any], replacement: dict[str, Any], known_chunks: set[str], known_nodes: set[str]) -> dict[str, Any]:
    if replacement.get("status") != "Confirmed":
        raise ValueError("TP005 replacement is not human-confirmed")
    replacement_id = str(replacement.get("original_annotation_id", ""))
    if replacement_id != "TP005":
        raise ValueError("replacement must supersede TP005")
    unknown_chunks = set(replacement.get("gold_evidence_chunk_ids") or []) - known_chunks
    unknown_nodes = set(replacement.get("accepted_graph_path_node_ids") or []) - known_nodes
    if unknown_chunks:
        raise ValueError(f"replacement refers to chunks outside frozen corpus: {sorted(unknown_chunks)}")
    if unknown_nodes:
        raise ValueError(f"replacement refers to missing graph nodes: {sorted(unknown_nodes)}")

    rows: list[dict[str, Any]] = []
    for source in provisional.get("queries") or []:
        annotation_id = str(source.get("annotation_id", ""))
        if annotation_id == replacement_id:
            row = dict(source)
            row.update({
                "query": replacement["query"],
                "original_query": source["query"],
                "revision_id": replacement["review_id"],
                "gold_evidence_chunk_ids": list(replacement["gold_evidence_chunk_ids"]),
                "accepted_graph_path_node_ids": list(replacement["accepted_graph_path_node_ids"]),
                "review_status": "reviewed",
                "eligible_for_formal_evaluation": True,
                "human_review_note": replacement["human_review_note"],
                "replacement_protocol": "one_for_one_replacement_of_excluded_TP005_before_freeze",
            })
            rows.append(row)
        elif str(source.get("review_status", "")).startswith("human_confirmed"):
            row = dict(source)
            if not row.get("gold_evidence_chunk_ids"):
                raise ValueError(f"confirmed row lacks gold chunks: {annotation_id}")
            unknown = set(row["gold_evidence_chunk_ids"]) - known_chunks
            if unknown:
                raise ValueError(f"confirmed row refers to chunks outside frozen corpus: {annotation_id}: {sorted(unknown)}")
            row.update({"review_status": "reviewed", "eligible_for_formal_evaluation": True})
            rows.append(row)

    ids = [str(row.get("annotation_id", "")) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate annotation IDs in finalized evaluation set")
    if len(rows) != 60:
        raise ValueError(f"expected exactly 60 final reviewed rows, found {len(rows)}")
    return {
        "schema_version": "1.0",
        "status": "reviewed_human_evaluation_set_pre_freeze",
        "formal_metrics_ready": False,
        "finalization_protocol": {
            "selection": "59 human-confirmed original/revised items plus one human-confirmed TP005 replacement",
            "replacement": "TP005 was excluded in the first review because its evidence reader omitted structured FDA shortage records. The replacement was independently human-reviewed before freezing.",
            "structured_evidence_policy": "FDA graph nodes support graph-path validation only and are never inserted into gold_evidence_chunk_ids or text-retrieval metrics.",
        },
        "source_provisional_registry": provisional.get("provisional_review_summary", {}),
        "queries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize and freeze the three-path human-reviewed evaluation set")
    parser.add_argument("--provisional", required=True)
    parser.add_argument("--replacement", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--reviewed-output", required=True)
    parser.add_argument("--frozen-output", required=True)
    args = parser.parse_args()
    reviewed_output = Path(args.reviewed_output)
    frozen_output = Path(args.frozen_output)
    if reviewed_output.exists() or frozen_output.exists():
        raise RuntimeError("refusing to overwrite a finalized evaluation artifact")
    provisional_path = Path(args.provisional)
    replacement_path = Path(args.replacement)
    reviewed = finalize(
        read_json(provisional_path),
        read_json(replacement_path),
        source_chunk_ids(Path(args.corpus)),
        graph_node_ids(Path(args.graph)),
    )
    reviewed["audit_sources"] = {
        "provisional_registry": str(provisional_path),
        "provisional_registry_sha256": sha256_file(provisional_path),
        "tp005_replacement_review": str(replacement_path),
        "tp005_replacement_review_sha256": sha256_file(replacement_path),
    }
    reviewed_output.parent.mkdir(parents=True, exist_ok=True)
    reviewed_output.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2), encoding="utf-8")
    frozen = freeze_pack(reviewed)
    frozen["source_pack"] = str(reviewed_output)
    frozen["source_pack_sha256"] = sha256_file(reviewed_output)
    frozen["audit_sources"] = reviewed["audit_sources"]
    frozen_output.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reviewed_queries": len(reviewed["queries"]), "frozen_queries": len(frozen["queries"]), "review_ledger": frozen["review_ledger"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
