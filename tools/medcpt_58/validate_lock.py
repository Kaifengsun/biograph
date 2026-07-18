"""Validate the MedCPT lock against all frozen inputs, models, and code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.medcpt_58.common import (
    ROOT,
    corpus_manifest,
    runtime_model_manifest,
    read_json,
    sha256_file,
    sha256_json,
)


def validate_lock(lock: dict[str, Any], lock_path: Path) -> dict[str, Any]:
    inputs = lock["inputs"]
    checks = {
        "status_locked_before_scores": lock.get("status") == "locked_before_feedback_motivated_medcpt_scores",
        "results_unobserved_at_lock": lock.get("results_observed_at_lock") is False,
        "pack_hash_matches": sha256_file(ROOT / inputs["pack_path"]) == inputs["pack_sha256"],
        "bm25_hash_matches": sha256_file(ROOT / inputs["bm25_candidates_path"]) == inputs["bm25_candidates_sha256"],
        "dense_corpus_hash_matches": sha256_file(ROOT / inputs["dense_corpus_path"]) == inputs["dense_corpus_sha256"],
        "corpus_manifest_matches": (
            sha256_json(corpus_manifest(ROOT / inputs["corpus_path"]))
            == inputs["corpus_manifest_sha256"]
        ),
        "query_count_is_58": lock["evaluation"]["query_count"] == 58,
        "no_fine_tuning": lock["inference"]["fine_tuning"] is False,
        "role_is_locked_extension": lock["evaluation"]["role"] == "feedback_motivated_locked_extension",
    }
    for name, model in lock["models"].items():
        current = runtime_model_manifest(ROOT / model["local_path"])
        checks[f"{name}_model_manifest_matches"] = sha256_json(current) == model["manifest_sha256"]
    code_checks = {
        path: sha256_file(ROOT / path) == expected
        for path, expected in lock["code_hashes"].items()
    }
    checks["all_code_hashes_match"] = all(code_checks.values())
    return {
        "schema_version": "1.0",
        "lock_path": str(lock_path),
        "checks": checks,
        "code_checks": code_checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    args = parser.parse_args()
    report = validate_lock(read_json(args.lock), args.lock)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
