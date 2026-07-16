"""Validate and evaluate the locked supplementary BGE reranker output."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.modern_reranker_58.common import (
    ROOT, aggregate, metric_row, paired_bootstrap, read_json, sha256_file, write_json,
)
from tools.modern_reranker_58.validate_lock import validate_lock


METRICS = ("hit_at_1", "hit_at_3", "hit_at_5", "hit_at_50", "mrr_at_50", "ndcg_at_5")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--inference", required=True, type=Path)
    parser.add_argument("--evaluation", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    lock = read_json(args.lock)
    lock_report = validate_lock(lock, args.lock)
    inference = read_json(args.inference)
    candidates = read_json(ROOT / lock["inputs"]["candidates_path"])
    source_by_id = {row["annotation_id"]: row for row in candidates["queries"]}
    output_by_id = {row["annotation_id"]: row for row in inference.get("queries", [])}
    expected_ids = [row["annotation_id"] for row in candidates["queries"]]
    checks = {
        "lock_valid": lock_report["passed"],
        "inference_complete": inference.get("status") == "complete",
        "all_58_queries_present": list(output_by_id) == expected_ids,
        "all_rankings_have_50": all(len(row["ranking"]) == 50 for row in output_by_id.values()),
        "all_rankings_unique": all(len({item["chunk_id"] for item in row["ranking"]}) == 50 for row in output_by_id.values()),
        "all_candidates_preserved": all(
            {item["chunk_id"] for item in output_by_id[query_id]["ranking"]}
            == {item["chunk_id"] for item in source_by_id[query_id]["candidates"]}
            for query_id in expected_ids
        ),
        "posthoc_role": inference.get("evaluation_role") == "supplementary_posthoc",
    }
    if not all(checks.values()):
        report = {"schema_version": "1.0", "checks": checks, "passed": False}
        write_json(args.report, report)
        raise SystemExit(json.dumps(report, indent=2))

    per_query: list[dict] = []
    for query_id in expected_ids:
        source = source_by_id[query_id]
        output = output_by_id[query_id]
        gold = set(source["gold_evidence_chunk_ids"])
        bm25 = [row["chunk_id"] for row in source["candidates"]]
        bge = [row["chunk_id"] for row in output["ranking"]]
        per_query.append({
            "annotation_id": query_id,
            "query_slice": source["query_slice"],
            "metrics": {"BM25_context_matched": metric_row(bm25, gold), "BGE_posthoc_reranker": metric_row(bge, gold)},
            "rankings": {"BM25_context_matched": bm25, "BGE_posthoc_reranker": bge},
        })
    methods = ("BM25_context_matched", "BGE_posthoc_reranker")
    aggregate_rows = {method: aggregate(row["metrics"][method] for row in per_query) for method in methods}
    paired = {
        metric: paired_bootstrap(
            [row["metrics"]["BGE_posthoc_reranker"][metric] for row in per_query],
            [row["metrics"]["BM25_context_matched"][metric] for row in per_query],
            seed=lock["evaluation"]["bootstrap_seed"],
            iterations=lock["evaluation"]["bootstrap_iterations"],
        )
        for metric in METRICS
    }
    slices = sorted({row["query_slice"] for row in per_query})
    by_slice = {
        query_slice: {
            method: aggregate(row["metrics"][method] for row in per_query if row["query_slice"] == query_slice)
            for method in methods
        }
        for query_slice in slices
    }
    evaluation = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "evaluation_role": "supplementary_posthoc",
        "query_count": 58,
        "methods": list(methods),
        "metrics": list(METRICS),
        "aggregate": aggregate_rows,
        "paired_bootstrap_bge_minus_bm25": paired,
        "by_slice": by_slice,
        "per_query": per_query,
        "input_hashes": {"lock": sha256_file(args.lock), "inference": sha256_file(args.inference)},
    }
    write_json(args.evaluation, evaluation)
    report = {
        "schema_version": "1.0",
        "checks": checks,
        "reported_all_prespecified_metrics": list(METRICS) == lock["evaluation"]["metrics"],
        "passed": all(checks.values()) and list(METRICS) == lock["evaluation"]["metrics"],
        "evaluation_sha256": sha256_file(args.evaluation),
    }
    write_json(args.report, report)
    print(json.dumps({"aggregate": aggregate_rows, "paired": paired, "checks": report}, indent=2))


if __name__ == "__main__":
    main()
