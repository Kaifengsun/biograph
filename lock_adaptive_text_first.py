"""Create an immutable method-lock manifest after development and tests pass."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DEVELOPMENT = Path("outputs/adaptive_text_first_development_2026-07-15-v3/development_report.json")
DEFAULT_PENDING = Path("data/eval/adaptive_text_first_heldout_frozen_pending_method_lock_2026-07-15.json")
DEFAULT_TEST_LOG = Path("outputs/adaptive_text_first_development_2026-07-15-v3/full_test_suite.txt")
DEFAULT_OUTPUT = Path("outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json")
DEFAULT_GRAPH = Path("artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda")
DEFAULT_INDEX = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-report", default=str(DEFAULT_DEVELOPMENT))
    parser.add_argument("--pending-heldout", default=str(DEFAULT_PENDING))
    parser.add_argument("--test-log", default=str(DEFAULT_TEST_LOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH))
    parser.add_argument("--index-root", default=str(DEFAULT_INDEX))
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite method lock: {output}")
    development_path = Path(args.development_report)
    pending_path = Path(args.pending_heldout)
    test_log_path = Path(args.test_log)
    development = read_json(development_path)
    pending = read_json(pending_path)
    test_log = test_log_path.read_text(encoding="utf-8", errors="replace")
    if development.get("heldout_executed") is not False:
        raise ValueError("development report does not certify that held-out queries were untouched")
    if pending.get("retrieval_execution_prohibited") is not True or pending.get("formal_metrics_ready") is not False:
        raise ValueError("pending held-out pack is not protected by the execution gate")
    if "OK" not in test_log or "FAILED" in test_log or "ERROR" in test_log:
        raise ValueError("full test log does not contain a clean OK result")

    project_files = [
        Path("adaptive_text_first.py"),
        Path("develop_adaptive_text_first.py"),
        Path("evaluate_adaptive_text_first.py"),
        Path("run_three_path_pilot.py"),
        Path("three_path_retrieval.py"),
        Path("three_path_evaluation.py"),
        Path("activate_adaptive_heldout.py"),
    ]
    graph = Path(args.graph)
    index_root = Path(args.index_root)
    indexed_files = [
        index_root / variant / file_name
        for variant in ("R2_summary", "R3_hyde")
        for file_name in ("pharma_docs.faiss", "pharma_docs.meta.json")
    ]
    files = project_files + indexed_files + [graph / "nodes.jsonl", graph / "edges.jsonl"]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"method-lock inputs are missing: {missing}")
    manifest = {
        "schema_version": "1.0",
        "lock_status": "locked_for_single_heldout_execution",
        "locked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "heldout_executed_before_lock": False,
        "selection_dataset": "60-query development set",
        "selected_parameters": development["selected"]["parameters"],
        "selection_rule": development["selection_rule"],
        "declared_variants": [
            "bottom_up", "top_down", "graph_path", "text_rrf", "unconditional_three_path_rrf",
            "adaptive_without_graph", "adaptive_full",
        ],
        "development_quality_checks": development["quality_checks"],
        "inputs": {
            "development_report": {"path": str(development_path), "sha256": sha256_file(development_path)},
            "pending_heldout": {"path": str(pending_path), "sha256": sha256_file(pending_path)},
            "test_log": {"path": str(test_log_path), "sha256": sha256_file(test_log_path)},
            "files": {str(path): sha256_file(path) for path in files},
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "lock_status": manifest["lock_status"], "selected_parameters": manifest["selected_parameters"]}, indent=2))


if __name__ == "__main__":
    main()
