"""Verify the locked method and activate the human-reviewed confirmatory pack once."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from develop_source_chunk_reranker import query_hash


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_question(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", default="data/eval/selective_reranker_confirmatory_frozen_pending_2026-07-16.json")
    parser.add_argument("--lock", default="outputs/selective_source_chunk_reranker_method_lock_2026-07-15/method_lock_manifest.json")
    parser.add_argument("--review-payload", default="outputs/selective_source_chunk_reranker_confirmatory_review_2026-07-16/review_payload.json")
    parser.add_argument("--output", default="data/eval/selective_reranker_confirmatory_frozen_run_ready_2026-07-16.json")
    args = parser.parse_args()

    pending_path, lock_path = Path(args.pending), Path(args.lock)
    review_payload_path, output_path = Path(args.review_payload), Path(args.output)
    if output_path.exists():
        raise RuntimeError(f"refusing to overwrite run-ready pack: {output_path}")
    pending, lock, review_payload = read_json(pending_path), read_json(lock_path), read_json(review_payload_path)
    if pending.get("status") != "frozen_human_reviewed_confirmatory_pending_activation":
        raise ValueError("pending pack has unexpected status")
    if not pending.get("confirmatory_for_source_chunk_reranker"):
        raise ValueError("pending pack is not dedicated to the source-chunk reranker")
    if lock.get("lock_status") != "locked_before_confirmatory_set_construction":
        raise ValueError("method lock has unexpected status")

    actual_lock_hash = sha256_file(lock_path)
    declared_lock_hash = review_payload.get("method_lock", {}).get("sha256")
    if actual_lock_hash != declared_lock_hash:
        raise ValueError("method-lock hash differs from the lock declared before blind review")
    changed_inputs = []
    for raw_path, expected_hash in lock.get("inputs", {}).items():
        file_path = Path(raw_path)
        if not file_path.exists() or sha256_file(file_path) != expected_hash:
            changed_inputs.append(raw_path)
    if changed_inputs:
        raise ValueError(f"locked inputs changed after method lock: {changed_inputs[:5]}")

    queries = pending.get("queries", [])
    if len(queries) != 30:
        raise ValueError("confirmatory pack must contain exactly 30 queries")
    expected_slices = {"single_clause": 10, "table": 8, "document_structure": 6, "cross_document": 6}
    actual_slices = {name: sum(row["query_slice"] == name for row in queries) for name in expected_slices}
    if actual_slices != expected_slices:
        raise ValueError(f"slice mismatch: {actual_slices}")

    prior_paths = [
        Path("data/eval/three_path_evaluation_frozen_2026-07-15.json"),
        Path("data/eval/bm25_enrichment_heldout_frozen_run_ready_2026-07-15.json"),
    ]
    prior_rows = [row for path in prior_paths for row in read_json(path).get("queries", [])]
    prior_ids = {str(row["annotation_id"]) for row in prior_rows}
    prior_questions = {normalized_question(str(row["query"])) for row in prior_rows}
    current_ids = {str(row["annotation_id"]) for row in queries}
    current_questions = {normalized_question(str(row["query"])) for row in queries}
    if current_ids & prior_ids:
        raise ValueError("confirmatory annotation IDs overlap the 90 observed queries")
    if current_questions & prior_questions:
        raise ValueError("confirmatory questions overlap the 90 observed queries")

    activated = deepcopy(pending)
    activated.update({
        "status": "frozen_human_reviewed_confirmatory_run_ready",
        "formal_metrics_ready": True,
        "retrieval_execution_prohibited": False,
        "activated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "query_content_sha256": query_hash(queries),
        "method_lock": {"path": str(lock_path), "sha256": actual_lock_hash},
        "activation_checks": {
            "all_locked_input_hashes_unchanged": True,
            "method_lock_matches_blind_review_payload": True,
            "prior_90_annotation_id_overlap": 0,
            "prior_90_normalized_question_overlap": 0,
            "single_formal_execution_authorized": True,
        },
    })
    output_path.write_text(json.dumps(activated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "status": activated["status"],
        "query_count": len(queries),
        "query_content_sha256": activated["query_content_sha256"],
        "activation_checks": activated["activation_checks"],
    }, indent=2))


if __name__ == "__main__":
    main()
