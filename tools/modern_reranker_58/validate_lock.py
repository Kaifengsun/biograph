"""Validate that a post-hoc reranker lock still matches every frozen input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.modern_reranker_58.common import (
    ROOT, corpus_manifest, read_json, sha256_file, sha256_json,
)


def validate_lock(lock: dict[str, Any], lock_path: Path) -> dict[str, Any]:
    candidates_path = ROOT / lock["inputs"]["candidates_path"]
    pack_path = ROOT / lock["inputs"]["pack_path"]
    corpus_path = ROOT / lock["inputs"]["corpus_path"]
    checks = {
        "status_locked_before_scores": lock.get("status") == "locked_before_posthoc_neural_scores",
        "results_unobserved_at_lock": lock.get("results_observed_at_lock") is False,
        "pack_hash_matches": sha256_file(pack_path) == lock["inputs"]["pack_sha256"],
        "candidates_hash_matches": sha256_file(candidates_path) == lock["inputs"]["candidates_sha256"],
        "corpus_manifest_matches": sha256_json(corpus_manifest(corpus_path)) == lock["inputs"]["corpus_manifest_sha256"],
        "candidate_depth_is_50": lock["inference"]["candidate_depth"] == 50,
        "max_length_is_512": lock["inference"]["max_length"] == 512,
        "no_fine_tuning": lock["inference"]["fine_tuning"] is False,
        "posthoc_label": lock["evaluation"]["role"] == "supplementary_posthoc",
    }
    code_checks: dict[str, bool] = {}
    for relative_path, expected_hash in lock["code_hashes"].items():
        code_checks[relative_path] = sha256_file(ROOT / relative_path) == expected_hash
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
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate_lock(read_json(args.lock), args.lock)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
