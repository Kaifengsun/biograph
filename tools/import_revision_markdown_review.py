"""Import a second-round Markdown review without creating formal labels.

Confirmed rows retain only human-supplied source chunks that are both present
in the frozen corpus and shown in the second-round candidate set.  The output
is an auditable review record; it is not yet a frozen evaluation set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_PACK = Path("data/eval/three_path_revision_round_2026-07-14-v2-with-retrieval.json")
DEFAULT_CORPUS = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_markdown(path: Path) -> dict[str, dict[str, str]]:
    decisions: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] == "Revision ID":
            continue
        review_id, status, gold, reason = cells[:4]
        status = status.replace("*", "").strip()
        if status not in {"Confirmed", "Revise", "Exclude"}:
            raise ValueError(f"unsupported review status for {review_id}: {status}")
        if review_id in decisions:
            raise ValueError(f"duplicate review ID: {review_id}")
        chunk_ids = re.findall(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+", gold)
        decisions[review_id] = {"status": status, "gold": ";".join(chunk_ids), "reason": reason}
    if not decisions:
        raise ValueError("no review rows found")
    return decisions


def corpus_chunk_ids(corpus: Path) -> set[str]:
    ids: set[str] = set()
    for path in corpus.glob("*_enriched.json"):
        for row in read_json(path):
            if row.get("chunk_id"):
                ids.add(str(row["chunk_id"]))
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Import second-round Markdown review decisions")
    parser.add_argument("--review", required=True)
    parser.add_argument("--pack", default=str(DEFAULT_PACK))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output}")

    review_path = Path(args.review)
    pack = read_json(Path(args.pack))
    decisions = parse_markdown(review_path)
    rows = pack["queries"]
    by_id = {str(row["annotation_id"]): row for row in rows}
    if set(decisions) != set(by_id):
        raise ValueError("review IDs must exactly match second-round pack IDs")
    known_chunks = corpus_chunk_ids(Path(args.corpus))
    confirmed = revised = excluded = 0
    for row in rows:
        decision = decisions[str(row["annotation_id"])]
        status = decision["status"]
        row["human_review_status"] = status
        row["human_review_note"] = decision["reason"]
        if status == "Confirmed":
            gold = [value for value in decision["gold"].split(";") if value]
            if not gold:
                raise ValueError(f"Confirmed row lacks gold evidence: {row['annotation_id']}")
            unknown = [value for value in gold if value not in known_chunks]
            if unknown:
                raise ValueError(f"unknown frozen chunk(s) for {row['annotation_id']}: {unknown}")
            candidates = set(row.get("candidate_evidence_chunk_ids") or [])
            outside = [value for value in gold if value not in candidates]
            if outside:
                raise ValueError(f"gold chunks not shown to reviewer for {row['annotation_id']}: {outside}")
            row["gold_evidence_chunk_ids"] = gold
            row["review_status"] = "human_confirmed_second_round"
            confirmed += 1
        elif status == "Revise":
            row["gold_evidence_chunk_ids"] = []
            row["review_status"] = "human_revise_second_round"
            revised += 1
        else:
            row["gold_evidence_chunk_ids"] = []
            row["review_status"] = "human_exclude_second_round"
            excluded += 1
        row["eligible_for_formal_evaluation"] = False

    source_hash = hashlib.sha256(review_path.read_bytes()).hexdigest()
    result = dict(pack)
    result["status"] = "second_round_human_review_record_not_formal"
    result["formal_metrics_ready"] = False
    result["human_review_import"] = {
        "source_file": str(review_path),
        "source_sha256": source_hash,
        "confirmed": confirmed,
        "revise": revised,
        "exclude": excluded,
        "formal_gold_labels_created": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["human_review_import"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
