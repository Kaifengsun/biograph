"""Freeze a reviewed three-path subset only when predeclared quality gates pass."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from three_path_evaluation import FROZEN_STATUS, review_ledger, sha256_file


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_pack(pack: dict[str, Any], min_total: int = 60, min_table: int = 10, min_cross_or_path: int = 15) -> dict[str, Any]:
    rows = list(pack.get("queries") or [])
    eligible = [row for row in rows if row.get("review_status") == "reviewed" and row.get("eligible_for_formal_evaluation")]
    invalid = [str(row.get("annotation_id", "")) for row in eligible if not row.get("gold_evidence_chunk_ids")]
    if invalid:
        raise ValueError(f"reviewed rows missing gold evidence: {invalid}")
    table_count = sum(row.get("query_slice") == "table" for row in eligible)
    cross_or_path_count = sum(row.get("query_slice") in {"cross_document", "supply_chain_evidence_path"} for row in eligible)
    if len(eligible) < min_total:
        raise ValueError(f"need at least {min_total} eligible rows, found {len(eligible)}")
    if table_count < min_table:
        raise ValueError(f"need at least {min_table} eligible table rows, found {table_count}")
    if cross_or_path_count < min_cross_or_path:
        raise ValueError(f"need at least {min_cross_or_path} eligible cross-document/path rows, found {cross_or_path_count}")
    return {
        "schema_version": "1.0",
        "status": FROZEN_STATUS,
        "formal_metrics_ready": True,
        "frozen_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "freeze_requirements": {"min_total": min_total, "min_table": min_table, "min_cross_document_or_path": min_cross_or_path},
        "review_ledger": review_ledger(rows),
        "queries": eligible,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a human-reviewed three-path evaluation subset")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-total", type=int, default=60)
    parser.add_argument("--min-table", type=int, default=10)
    parser.add_argument("--min-cross-or-path", type=int, default=15)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing frozen evaluation snapshot: {output}")
    pack_path = Path(args.pack)
    frozen = freeze_pack(read_json(pack_path), args.min_total, args.min_table, args.min_cross_or_path)
    frozen["source_pack"] = str(pack_path)
    frozen["source_pack_sha256"] = sha256_file(pack_path)
    output.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"eligible_rows": len(frozen["queries"]), "review_ledger": frozen["review_ledger"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
