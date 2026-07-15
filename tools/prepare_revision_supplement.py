"""Prepare a compact re-review pack with preserved first-round candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_REVIEWED = Path("data/eval/three_path_revision_round_2026-07-14-human-reviewed.json")
DEFAULT_ORIGINAL = Path("data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a legacy-evidence supplement for unresolved revisions")
    parser.add_argument("--reviewed", default=str(DEFAULT_REVIEWED))
    parser.add_argument("--original-pack", default=str(DEFAULT_ORIGINAL))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output}")

    reviewed = read_json(Path(args.reviewed))
    original_by_id = {str(row["annotation_id"]): row for row in read_json(Path(args.original_pack))["queries"]}
    selected = []
    for row in reviewed["queries"]:
        if row.get("human_review_status") != "Revise":
            continue
        source = original_by_id[str(row["original_annotation_id"])]
        merged = dict(row)
        merged["candidate_evidence_chunk_ids"] = sorted(set(row.get("candidate_evidence_chunk_ids") or []) | set(source.get("candidate_evidence_chunk_ids") or []))
        merged["candidate_document_ids"] = sorted(set(row.get("candidate_document_ids") or []) | set(source.get("candidate_document_ids") or []))
        merged["legacy_candidate_evidence_chunk_ids"] = list(source.get("candidate_evidence_chunk_ids") or [])
        merged["legacy_candidate_source"] = str(args.original_pack)
        merged["review_status"] = "supplement_requires_human_review"
        merged["gold_evidence_chunk_ids"] = []
        merged["eligible_for_formal_evaluation"] = False
        selected.append(merged)
    if not selected:
        raise ValueError("no unresolved Revise rows in reviewed input")
    selected.sort(key=lambda row: row["annotation_id"])
    result = {
        "schema_version": "1.0",
        "status": "supplemental_legacy_evidence_review_not_formal",
        "formal_metrics_ready": False,
        "counts": {"queries": len(selected)},
        "review_requirements": reviewed.get("review_requirements", []),
        "queries": selected,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "queries": len(selected)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
