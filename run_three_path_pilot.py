"""Run an immutable engineering pilot for the three-path snapshot retriever."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from three_path_retrieval import ThreePathSnapshotRetriever, stable_run_id


DEFAULT_QUERIES = Path("data/eval/three_path_label_template_2026-07-11.json")


def read_queries(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("retrieval_execution_prohibited") is True:
        raise ValueError("query bundle is frozen but retrieval execution remains prohibited pending method lock")
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("query bundle must contain a list of queries")
    valid = [row for row in rows if str(row.get("query", "")).strip()]
    if not valid:
        raise ValueError("query bundle contains no executable query")
    return valid


def main() -> None:
    parser = argparse.ArgumentParser(description="Run three-path retrieval engineering pilot")
    parser.add_argument("--queries", default=str(DEFAULT_QUERIES))
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--document-budget", type=int, default=2)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-states", type=int, default=800)
    args = parser.parse_args()
    query_path = Path(args.queries)
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing pilot output: {output}")
    queries = read_queries(query_path)
    if args.limit:
        queries = queries[:args.limit]
    retriever = ThreePathSnapshotRetriever()
    query_vectors = retriever.encode_queries([str(row["query"]) for row in queries])
    results = []
    for row, query_vector in zip(queries, query_vectors):
        results.append({
            "query_id": row.get("query_id") or row.get("annotation_id", ""),
            "query_slice": row.get("query_slice", ""),
            "retrieval": retriever.retrieve_all(
                str(row["query"]),
                k=args.k,
                document_budget=args.document_budget,
                max_depth=args.max_depth,
                max_state_expansions=args.max_states,
                query_vector=query_vector.reshape(1, -1),
            ),
        })
    output.mkdir(parents=True)
    (output / "per_query.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "run_type": "three_path_engineering_pilot",
        "formal_metrics": False,
        "label_status": "review_template_only_no_gold_evidence",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "query_bundle": str(query_path),
        "query_bundle_run_id": stable_run_id(query_path),
        "query_count": len(results),
        "parameters": {"k": args.k, "document_budget": args.document_budget, "max_depth": args.max_depth, "max_state_expansions": args.max_states},
        "input_hashes": retriever.input_hashes(),
        "canonical_artifacts_replaced": False,
    }
    (output / "pilot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"query_count": len(results), "formal_metrics": False, "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
