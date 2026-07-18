"""Evaluate every locked MedCPT method against BM25 without selective reporting."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.medcpt_58.common import (
    METRICS,
    ROOT,
    evaluate_rankings,
    paired_bootstrap,
    read_json,
    sha256_file,
    write_json,
)
from tools.medcpt_58.validate_lock import validate_lock


METHODS = ("BM25", "MedCPT_dual_encoder", "BM25_then_MedCPT_cross_encoder")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--inference", required=True, type=Path)
    parser.add_argument("--evaluation", required=True, type=Path)
    args = parser.parse_args()
    lock = read_json(args.lock)
    if not validate_lock(lock, args.lock)["passed"]:
        raise RuntimeError("lock validation failed")
    inference = read_json(args.inference)
    if inference.get("status") != "complete" or inference.get("lock_sha256") != sha256_file(args.lock):
        raise ValueError("inference is incomplete or belongs to another lock")
    pack = read_json(ROOT / lock["inputs"]["pack_path"])
    bm25 = read_json(ROOT / lock["inputs"]["bm25_candidates_path"])
    bm25_by_id = {row["annotation_id"]: row for row in bm25["queries"]}
    output_by_id = {row["annotation_id"]: row for row in inference["queries"]}
    expected_ids = [row["annotation_id"] for row in pack["queries"]]
    if list(output_by_id) != expected_ids:
        raise ValueError("inference query order does not match the frozen pack")

    rankings = {}
    for query_id in expected_ids:
        rankings[query_id] = {
            "BM25": [row["chunk_id"] for row in bm25_by_id[query_id]["candidates"]],
            "MedCPT_dual_encoder": [
                row["chunk_id"] for row in output_by_id[query_id]["medcpt_dual_encoder_ranking"]
            ],
            "BM25_then_MedCPT_cross_encoder": [
                row["chunk_id"] for row in output_by_id[query_id]["medcpt_cross_encoder_ranking"]
            ],
        }
    result = evaluate_rankings(pack["queries"], rankings, METHODS)
    paired = {}
    for treatment in METHODS[1:]:
        paired[f"{treatment}_minus_BM25"] = {
            metric: paired_bootstrap(
                [row["metrics"][treatment][metric] for row in result["per_query"]],
                [row["metrics"]["BM25"][metric] for row in result["per_query"]],
                iterations=lock["evaluation"]["bootstrap_iterations"],
                seed=lock["evaluation"]["bootstrap_seed"],
            )
            for metric in METRICS
        }
    payload = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "evaluation_role": lock["evaluation"]["role"],
        "query_count": 58,
        "methods": list(METHODS),
        "metrics": list(METRICS),
        **result,
        "paired_bootstrap": paired,
        "input_hashes": {"lock": sha256_file(args.lock), "inference": sha256_file(args.inference)},
    }
    write_json(args.evaluation, payload)
    print(json.dumps({"aggregate": payload["aggregate"], "paired_bootstrap": paired}, indent=2))


if __name__ == "__main__":
    main()
