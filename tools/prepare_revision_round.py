"""Create a traceable second-round review pack from the user's DOCX decisions.

The script intentionally uses the exact English replacement question recorded in
the review document.  It does not ask an LLM to rewrite or broaden questions.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from docx import Document


DEFAULT_REVIEW_DOC = Path("outputs/实验审核结果.docx")
DEFAULT_BASE_PACK = Path("data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def revised_question(note: str) -> str:
    """Extract the final English question after the reviewer recommendation."""
    end = note.rfind("?")
    if end < 0:
        raise ValueError(f"review note has no proposed question: {note}")
    markers = [note.rfind(":", 0, end), note.rfind(chr(0xFF1A), 0, end)]
    start = max(markers) + 1
    result = note[start : end + 1].strip()
    if not re.match(r"^[A-Za-z]", result):
        raise ValueError(f"could not isolate an English revised question: {result}")
    return result


def collect_revisions(review_doc: Path) -> dict[str, dict[str, str]]:
    document = Document(review_doc)
    revisions: dict[str, dict[str, str]] = {}
    for table in document.tables:
        for row in table.rows[1:]:
            values = [cell.text.strip() for cell in row.cells]
            if len(values) < 4 or values[0] == "Review ID" or values[1] != "Revise":
                continue
            review_id, _status, _gold, note = values[:4]
            if review_id in revisions:
                raise ValueError(f"duplicate Revise decision for {review_id}")
            revisions[review_id] = {
                "revision_note": note,
                "revised_question": revised_question(note),
            }
    if not revisions:
        raise ValueError("no Revise rows were found in the review document")
    return revisions


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare second-round human review queries")
    parser.add_argument("--review-doc", default=str(DEFAULT_REVIEW_DOC))
    parser.add_argument("--base-pack", default=str(DEFAULT_BASE_PACK))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing revision pack: {output}")

    base_pack = read_json(Path(args.base_pack))
    base_by_id = {str(row["annotation_id"]): row for row in base_pack["queries"]}
    revisions = collect_revisions(Path(args.review_doc))
    rows = []
    for original_id, revision in revisions.items():
        base = base_by_id.get(original_id)
        if not base:
            raise ValueError(f"review ID {original_id} is absent from the base annotation pack")
        rows.append({
            "annotation_id": f"{original_id}__R1",
            "query_id": f"{original_id}__R1",
            "original_annotation_id": original_id,
            "original_query": str(base["query"]),
            "query": revision["revised_question"],
            "query_slice": str(base.get("query_slice", "")),
            "revision_note": revision["revision_note"],
            "candidate_evidence_chunk_ids": [],
            "candidate_document_ids": [],
            "candidate_graph_path_node_ids": [],
            "gold_evidence_chunk_ids": [],
            "accepted_graph_path_node_ids": [],
            "review_status": "unreviewed",
            "eligible_for_formal_evaluation": False,
            "exclusion_reason": "",
            "sources": [{
                "file": str(args.review_doc),
                "source_id": original_id,
                "decision": "Revise",
            }],
        })
    rows.sort(key=lambda row: row["annotation_id"])
    payload = {
        "schema_version": "1.0",
        "status": "second_round_candidate_pack_requires_human_review",
        "formal_metrics_ready": False,
        "counts": {"revised_queries": len(rows)},
        "review_requirements": [
            "Use the original source passage, not the LLM rationale, to decide Confirmed, Revise, or Exclude.",
            "Set Confirmed only when one or more source chunk IDs directly support the revised question.",
            "For entity or cross-document questions, inspect graph paths only after source passages; a path alone is not evidence.",
        ],
        "queries": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "revised_queries": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
