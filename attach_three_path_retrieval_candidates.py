"""Attach engineering retrieval candidates to a non-formal annotation pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_regulatory_evidence_graph import normalize_alias


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def attach_candidates(pack: dict[str, Any], retrieval_rows: list[dict[str, Any]], retrieval_source: str) -> dict[str, Any]:
    by_query = {normalize_alias(row["retrieval"]["query"]): row["retrieval"] for row in retrieval_rows}
    attached = 0
    for row in pack["queries"]:
        retrieval = by_query.get(normalize_alias(row["query"]))
        if not retrieval:
            continue
        evidence = []
        evidence.extend(retrieval.get("bottom_up") or [])
        evidence.extend((retrieval.get("top_down") or {}).get("evidence") or [])
        evidence.extend((retrieval.get("graph_path") or {}).get("evidence") or [])
        row["retrieval_candidate_evidence_chunk_ids"] = sorted({item["chunk_id"] for item in evidence if item.get("chunk_id")})
        row["candidate_evidence_chunk_ids"] = sorted(set(row["candidate_evidence_chunk_ids"]) | set(row["retrieval_candidate_evidence_chunk_ids"]))
        row["retrieval_candidate_graph_paths"] = [
            path.get("node_ids", [])
            for path in (retrieval.get("graph_path") or {}).get("paths", [])[:5]
        ]
        row["retrieval_candidate_source"] = retrieval_source
        attached += 1
    result = dict(pack)
    result["retrieval_candidate_attachment"] = {
        "source": retrieval_source,
        "attached_query_count": attached,
        "formal_metrics_ready": False,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach three-path retrieval candidates to annotation pack")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--retrieval", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing pack: {output}")
    pack = read_json(Path(args.pack))
    retrieval_rows = read_json(Path(args.retrieval))
    result = attach_candidates(pack, retrieval_rows, str(args.retrieval))
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["retrieval_candidate_attachment"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
