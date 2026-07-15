"""Activate a frozen held-out set only when its locked manifest matches exactly."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from three_path_evaluation import FROZEN_STATUS, validate_frozen_pack


DEFAULT_PENDING = Path("data/eval/adaptive_text_first_heldout_frozen_pending_method_lock_2026-07-15.json")
DEFAULT_LOCK = Path("outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json")
DEFAULT_OUTPUT = Path("data/eval/adaptive_text_first_heldout_frozen_run_ready_2026-07-15.json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def query_content_hash(queries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(queries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", default=str(DEFAULT_PENDING))
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    pending_path = Path(args.pending)
    lock_path = Path(args.lock)
    output_path = Path(args.output)
    if output_path.exists():
        raise RuntimeError(f"refusing to overwrite run-ready held-out set: {output_path}")
    pending = read_json(pending_path)
    lock = read_json(lock_path)
    if lock.get("lock_status") != "locked_for_single_heldout_execution":
        raise ValueError("method manifest is not locked")
    expected_hash = ((lock.get("inputs") or {}).get("pending_heldout") or {}).get("sha256")
    actual_hash = sha256_file(pending_path)
    if expected_hash != actual_hash:
        raise ValueError("pending held-out set changed after method lock")
    if pending.get("retrieval_execution_prohibited") is not True:
        raise ValueError("pending set is not protected before activation")

    activated = deepcopy(pending)
    before_hash = query_content_hash(activated["queries"])
    activated["status"] = FROZEN_STATUS
    activated["formal_metrics_ready"] = True
    activated["retrieval_execution_prohibited"] = False
    activated["activated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    activated["method_lock"] = {"path": str(lock_path), "sha256": sha256_file(lock_path)}
    activated["query_content_sha256"] = before_hash
    if query_content_hash(activated["queries"]) != before_hash:
        raise AssertionError("activation modified frozen query content")
    validate_frozen_pack(activated)
    output_path.write_text(json.dumps(activated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "status": activated["status"],
        "formal_metrics_ready": True,
        "query_count": len(activated["queries"]),
        "query_content_sha256": before_hash,
    }, indent=2))


if __name__ == "__main__":
    main()
