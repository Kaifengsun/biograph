"""Consolidate first- and second-round human review into a non-formal registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from docx import Document


DEFAULT_BASE = Path("data/eval/three_path_annotation_pack_2026-07-11-llm-assisted.json")
DEFAULT_FIRST_REVIEW = Path("outputs/实验审核结果.docx")
DEFAULT_SECOND_REVIEW = Path("data/eval/three_path_revision_round_2026-07-14-human-reviewed.json")
DEFAULT_SUPPLEMENT = Path("data/eval/three_path_revision_supplement_2026-07-14-human-reviewed.json")
DEFAULT_CORPUS = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")

# A first-round DOCX transcription typo; the corrected ID is present in the
# frozen corpus and was verified before consolidation.
CHUNK_ID_CORRECTIONS = {"ich_q11_C0051_e9462dc": "ich_q11_C0051_e9466bdc"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_chunk_ids(corpus: Path) -> set[str]:
    ids: set[str] = set()
    for path in corpus.glob("*_enriched.json"):
        for row in read_json(path):
            if row.get("chunk_id"):
                ids.add(str(row["chunk_id"]))
    return ids


def parse_first_round(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for table in Document(path).tables:
        for table_row in table.rows[1:]:
            values = [cell.text.strip() for cell in table_row.cells]
            if len(values) < 4 or values[0] == "Review ID":
                continue
            review_id, status, gold_text, note = values[:4]
            if status not in {"Confirmed", "Revise", "Exclude"}:
                continue
            gold = [CHUNK_ID_CORRECTIONS.get(value, value) for value in re.findall(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+", gold_text)]
            # DS007 appears twice in the DOCX. Its later second-round decision
            # supersedes both, so retain only the non-conflicting direct rows here.
            if review_id in rows and rows[review_id]["status"] != status:
                rows[review_id] = {"status": "Conflicted", "gold": [], "note": "first_round_duplicate_conflict"}
            else:
                rows[review_id] = {"status": status, "gold": gold, "note": note}
    return rows


def second_round_by_original(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_json(path)["queries"]
    return {str(row["original_annotation_id"]): row for row in rows if row.get("human_review_status") == "Confirmed"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build non-formal consolidated review registry")
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--first-review", default=str(DEFAULT_FIRST_REVIEW))
    parser.add_argument("--second-review", default=str(DEFAULT_SECOND_REVIEW))
    parser.add_argument("--supplement", default=str(DEFAULT_SUPPLEMENT))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output}")

    base = read_json(Path(args.base))
    first = parse_first_round(Path(args.first_review))
    second = second_round_by_original(Path(args.second_review))
    second.update(second_round_by_original(Path(args.supplement)))
    known = source_chunk_ids(Path(args.corpus))
    selected_ids = set(first)
    rows = []
    corrections = []
    for source in base["queries"]:
        row = dict(source)
        annotation_id = str(row["annotation_id"])
        if annotation_id in second:
            revised = second[annotation_id]
            gold = list(revised["gold_evidence_chunk_ids"])
            row.update({
                "query": revised["query"],
                "original_query": source["query"],
                "revision_id": revised["annotation_id"],
                "gold_evidence_chunk_ids": gold,
                "review_status": "human_confirmed_revised_question",
                "eligible_for_formal_evaluation": False,
                "human_review_note": revised.get("human_review_note", ""),
            })
        elif annotation_id in first:
            decision = first[annotation_id]
            if decision["status"] == "Confirmed":
                if not decision["gold"]:
                    raise ValueError(f"confirmed first-round decision lacks evidence: {annotation_id}")
                unknown = [value for value in decision["gold"] if value not in known]
                if unknown:
                    raise ValueError(f"unknown evidence for {annotation_id}: {unknown}")
                if any(value in CHUNK_ID_CORRECTIONS.values() for value in decision["gold"]):
                    corrections.append({"annotation_id": annotation_id, "correction": CHUNK_ID_CORRECTIONS})
                row.update({
                    "gold_evidence_chunk_ids": decision["gold"],
                    "review_status": "human_confirmed_first_round",
                    "eligible_for_formal_evaluation": False,
                    "human_review_note": decision["note"],
                })
            elif decision["status"] == "Exclude":
                row.update({
                    "gold_evidence_chunk_ids": [],
                    "review_status": "human_excluded_first_round",
                    "eligible_for_formal_evaluation": False,
                    "human_review_note": decision["note"],
                })
            elif decision["status"] == "Conflicted":
                row.update({"review_status": "requires_second_round_resolution", "eligible_for_formal_evaluation": False})
        rows.append(row)

    counts = Counter(row["review_status"] for row in rows)
    selected_confirmed = sum(row["review_status"].startswith("human_confirmed") and row["annotation_id"] in selected_ids for row in rows)
    result = dict(base)
    result.update({
        "status": "provisional_human_review_registry_not_formal",
        "formal_metrics_ready": False,
        "queries": rows,
        "provisional_review_summary": {
            "selected_first_round_ids": len(selected_ids),
            "selected_confirmed": selected_confirmed,
            "selected_excluded": sum(row["review_status"] == "human_excluded_first_round" and row["annotation_id"] in selected_ids for row in rows),
            "status_counts": dict(sorted(counts.items())),
            "chunk_id_corrections": corrections,
            "sources": {
                "first_review_docx_sha256": hashlib.sha256(Path(args.first_review).read_bytes()).hexdigest(),
                "second_round_json": str(args.second_review),
                "supplement_json": str(args.supplement),
            },
        },
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["provisional_review_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
