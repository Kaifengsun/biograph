"""Lock the source-chunk reranker before constructing its confirmatory set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", default="outputs/source_chunk_reranker_development_2026-07-15-v1/development_report.json")
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--output", default="outputs/source_chunk_reranker_method_lock_2026-07-15/method_lock_manifest.json")
    args = parser.parse_args()

    development_path, test_log, output = Path(args.development), Path(args.test_log), Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite method lock: {output}")
    development = json.loads(development_path.read_text(encoding="utf-8"))
    if development.get("dataset_role") != "development_only" or development.get("heldout_executed") is not False:
        raise ValueError("development report does not certify protected method development")
    if not all(development.get("quality_checks", {}).values()):
        raise ValueError("development quality checks are not clean")
    log_bytes = test_log.read_bytes()
    log = log_bytes.decode("utf-16") if b"\x00" in log_bytes[:200] else log_bytes.decode("utf-8", errors="replace")
    if "OK" not in log or re.search(r"^(?:FAILED|ERROR)(?:\s|$)", log, re.MULTILINE):
        raise ValueError("test log is not clean")

    corpus = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
    index = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4/R1_raw/pharma_docs.faiss")
    files = [
        Path("source_chunk_reranker.py"), Path("develop_source_chunk_reranker.py"),
        Path("evaluate_source_chunk_reranker.py"),
        Path("tests/test_source_chunk_reranker.py"),
        Path("docs/superpowers/specs/2026-07-15-source-chunk-reranking-design.md"),
        development_path, development_path.with_name("grid_results.json"),
        development_path.with_name("selected_per_query.json"),
        development_path.with_name("development_notes.md"),
        Path("data/eval/three_path_evaluation_frozen_2026-07-15.json"),
        Path("data/eval/bm25_enrichment_heldout_frozen_run_ready_2026-07-15.json"),
        index, index.with_suffix(".meta.json"), index.with_name("variant_manifest.json"),
        test_log,
    ]
    files.extend(sorted(corpus.glob("*_enriched.json")))
    files.extend(sorted(corpus.glob("*_tables.json")))
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(missing)

    manifest = {
        "schema_version": "1.0",
        "lock_status": "locked_before_confirmatory_set_construction",
        "locked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "new_confirmatory_set_executed_before_lock": False,
        "observed_validation_set_role": "exploratory_only",
        "development_query_content_sha256": development["query_content_sha256"],
        "selected_parameters": development["selected"]["parameters"],
        "declared_methods": ["BM25_context_matched", "R1_raw", "Global_source_RRF", "Query_routed_source_reranker"],
        "parameters": {
            "bm25_k1": 1.2, "bm25_b": 0.75,
            "source_payload": "parents_context+heading+content_first_2000_chars",
            "tokenization": "lowercase_ascii_alphanumeric",
            "embedding_model": "tencent/Youtu-Embedding",
            "dense_index": "IndexFlatIP_L2_normalized",
            "candidate_depth_per_channel": 30, "baseline_output_depth": 60,
            "rrf_k": 60, "bootstrap_iterations": 10000,
            "analysis_seed": 20260715, "confirmatory_sampling_seed": 20260716,
            "primary_outcome": "MRR_vs_BM25",
            "primary_minimum_effect": 0.03,
            "success_test": "paired_bootstrap_CI_and_Wilcoxon_with_Holm",
        },
        "inputs": {str(path): sha256_file(path) for path in files},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "file_count": len(files), "selected_parameters": manifest["selected_parameters"]}, indent=2))


if __name__ == "__main__":
    main()
