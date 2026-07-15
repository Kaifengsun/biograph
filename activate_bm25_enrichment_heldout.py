"""Activate the frozen BM25/enrichment held-out set after exact method locking."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", default="data/eval/bm25_enrichment_heldout_frozen_pending_method_lock_2026-07-15.json")
    parser.add_argument("--lock", default="outputs/bm25_enrichment_ablation_2026-07-15/method_lock_manifest.json")
    parser.add_argument("--output", default="data/eval/bm25_enrichment_heldout_frozen_run_ready_2026-07-15.json")
    args = parser.parse_args()
    pending, lock_path, output = Path(args.pending), Path(args.lock), Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite run-ready pack: {output}")
    pack = json.loads(pending.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("lock_status") != "locked_for_single_heldout_execution":
        raise ValueError("method is not locked")
    if lock["inputs"]["pending_heldout"]["sha256"] != sha256_file(pending):
        raise ValueError("pending held-out changed after lock")
    activated = deepcopy(pack)
    activated.update({"status": "frozen_human_reviewed_evaluation_set", "formal_metrics_ready": True, "retrieval_execution_prohibited": False, "activated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "method_lock": {"path": str(lock_path), "sha256": sha256_file(lock_path)}})
    if len(activated.get("queries", [])) != 30:
        raise ValueError("activated pack must contain 30 queries")
    output.write_text(json.dumps(activated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": activated["status"], "query_count": 30}, indent=2))


if __name__ == "__main__":
    main()
