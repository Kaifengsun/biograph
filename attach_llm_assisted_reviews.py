"""Attach non-formal LLM review suggestions to an annotation candidate pack."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def attach_reviews(pack: dict[str, Any], reviews: list[dict[str, Any]], source: str) -> dict[str, Any]:
    by_id = {row["annotation_id"]: row for row in reviews}
    attached = 0
    for row in pack["queries"]:
        review_row = by_id.get(row["annotation_id"])
        if not review_row:
            continue
        row["llm_assisted_review"] = review_row["review"]
        row["llm_assisted_review_model"] = review_row["model"]
        row["llm_assisted_review_prompt_version"] = review_row["prompt_version"]
        attached += 1
    result = dict(pack)
    result["llm_assisted_review_attachment"] = {
        "source": source,
        "attached_query_count": attached,
        "formal_metrics_ready": False,
        "formal_gold_labels_created": False,
        "suggested_insufficient_evidence": sum(
            bool(row["review"].get("insufficient_evidence")) for row in reviews
        ),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach LLM-assisted review suggestions")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output}")
    result = attach_reviews(read_json(Path(args.pack)), read_jsonl(Path(args.reviews)), args.reviews)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["llm_assisted_review_attachment"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
