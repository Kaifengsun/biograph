"""Lock all method and artifact inputs before the single held-out execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", default="data/eval/bm25_enrichment_heldout_frozen_pending_method_lock_2026-07-15.json")
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--output", default="outputs/bm25_enrichment_ablation_2026-07-15/method_lock_manifest.json")
    args = parser.parse_args()
    pending, test_log, output = Path(args.pending), Path(args.test_log), Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite method lock: {output}")
    pack = json.loads(pending.read_text(encoding="utf-8"))
    if pack.get("retrieval_execution_prohibited") is not True or pack.get("formal_metrics_ready") is not False:
        raise ValueError("pending held-out set is not protected")
    log_bytes = test_log.read_bytes()
    log = log_bytes.decode("utf-16") if b"\x00" in log_bytes[:200] else log_bytes.decode("utf-8", errors="replace")
    if "OK" not in log or re.search(r"^(?:FAILED|ERROR)(?:\s|$)", log, re.MULTILINE):
        raise ValueError("test log is not clean")
    index_root = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")
    files = [
        Path("evaluate_bm25_enrichment_ablation.py"), Path("adaptive_text_first.py"), Path("run_three_path_pilot.py"), Path("three_path_retrieval.py"), Path("tests/test_bm25_enrichment_evaluation.py"),
        Path("outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json"),
    ]
    for variant in ("R1_raw", "R2_summary", "R3_hyde", "R4_table"):
        files.extend([index_root / variant / "pharma_docs.faiss", index_root / variant / "pharma_docs.meta.json", index_root / variant / "variant_manifest.json"])
    corpus_files = sorted(Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4").glob("*_enriched.json")) + sorted(Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4").glob("*_tables.json"))
    files.extend(corpus_files)
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(missing)
    manifest = {
        "schema_version": "1.0", "lock_status": "locked_for_single_heldout_execution", "locked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "heldout_executed_before_lock": False,
        "declared_methods": ["BM25_raw", "R1_raw", "R2_summary", "R3_hyde", "R4_table", "BM25_R4_RRF", "Adaptive_text_first"],
        "parameters": {
            "bm25_k1": 1.2, "bm25_b": 0.75, "tokenization": "lowercase_alphanumeric",
            "dense_search_depth": 100, "source_chunk_deduplication": "highest_ranked_vector_occurrence",
            "rrf_k": 60, "rrf_weights": [1.0, 1.0],
            "adaptive_retrieval": {"k": 5, "document_budget": 2, "max_depth": 4, "max_state_expansions": 800},
            "bootstrap_iterations": 10000, "seed": 20260715,
        },
        "inputs": {"pending_heldout": {"path": str(pending), "sha256": sha256_file(pending)}, "test_log": {"path": str(test_log), "sha256": sha256_file(test_log)}, "files": {str(path): sha256_file(path) for path in files}},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "lock_status": manifest["lock_status"], "file_count": len(files)}, indent=2))


if __name__ == "__main__":
    main()
