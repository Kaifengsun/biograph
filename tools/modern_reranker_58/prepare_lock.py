"""Download an exact model revision and freeze BM25 candidates before scoring."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import transformers
from modelscope import snapshot_download
from modelscope.hub.api import HubApi

from tools.modern_reranker_58.common import (
    BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED, CANDIDATE_DEPTH, DEFAULT_CORPUS,
    DEFAULT_PACK, MODEL_ID, MODEL_MAX_LENGTH, ROOT, TASK_INSTRUCTION, corpus_manifest,
    model_manifest, prepare_bm25_candidates, sha256_file, sha256_json, write_json,
)


CODE_FILES = (
    "tools/modern_reranker_58/common.py",
    "tools/modern_reranker_58/validate_lock.py",
    "tools/modern_reranker_58/prepare_lock.py",
    "tools/modern_reranker_58/run_locked_reranker.py",
    "tools/modern_reranker_58/validate_results.py",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    if args.candidates.exists() or args.lock.exists():
        raise FileExistsError("candidate and lock outputs must not already exist")

    candidates = prepare_bm25_candidates(args.pack, args.corpus)
    write_json(args.candidates, candidates)
    model_info = HubApi().model_info(args.model_id, revision="master")
    revision = "master"
    snapshot = (
        args.model_dir.resolve()
        if args.model_dir
        else Path(snapshot_download(args.model_id, revision=revision))
    )
    if not snapshot.is_dir():
        raise FileNotFoundError(f"model directory does not exist: {snapshot}")
    model_files = model_manifest(snapshot)
    if not any(row["name"].endswith(".safetensors") for row in model_files):
        raise RuntimeError("downloaded model snapshot has no safetensors weights")

    lock = {
        "schema_version": "1.0",
        "status": "locked_before_posthoc_neural_scores",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "results_observed_at_lock": False,
        "one_shot_reporting_rule": True,
        "model": {
            "id": args.model_id,
            "source": "modelscope_official_qwen_repository",
            "source_url": f"https://www.modelscope.cn/models/{args.model_id}",
            "revision": revision,
            "source_last_updated": model_info.last_updated_time.isoformat(),
            "local_path": snapshot.relative_to(ROOT).as_posix(),
            "download_mode": "direct_modelscope_https" if args.model_dir else "modelscope_sdk",
            "license": "apache-2.0",
            "files": model_files,
            "manifest_sha256": sha256_json(model_files),
        },
        "inputs": {
            "pack_path": args.pack.resolve().relative_to(ROOT).as_posix(),
            "pack_sha256": sha256_file(args.pack),
            "corpus_path": args.corpus.resolve().relative_to(ROOT).as_posix(),
            "corpus_manifest_sha256": sha256_json(corpus_manifest(args.corpus)),
            "candidates_path": args.candidates.resolve().relative_to(ROOT).as_posix(),
            "candidates_sha256": sha256_file(args.candidates),
        },
        "inference": {
            "candidate_depth": CANDIDATE_DEPTH,
            "stored_ranking_depth": CANDIDATE_DEPTH,
            "presentation_depth": 5,
            "max_length": MODEL_MAX_LENGTH,
            "truncation": "longest_first_formatted_pair",
            "padding": "left_longest_in_batch",
            "task_instruction": TASK_INSTRUCTION,
            "score": "normalized_yes_probability_against_no",
            "unicode_normalization": "NFC",
            "payload_fields": ["parents_context", "heading", "content"],
            "payload_max_chars": 2000,
            "precision": "bfloat16",
            "device": "cuda:0",
            "batch_size": args.batch_size,
            "fine_tuning": False,
            "tie_break": ["score_desc", "bm25_rank_asc", "chunk_id_asc"],
            "raw_logit_abs_tolerance": 1e-5,
            "raw_logit_rel_tolerance": 1e-5,
        },
        "evaluation": {
            "role": "supplementary_posthoc",
            "metrics": ["hit_at_1", "hit_at_3", "hit_at_5", "hit_at_50", "mrr_at_50", "ndcg_at_5"],
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "gain": "binary",
            "resampling_unit": "query",
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "code_hashes": {path: sha256_file(ROOT / path) for path in CODE_FILES},
        "execution_command": (
            f"python -m tools.modern_reranker_58.run_locked_reranker --lock {args.lock.as_posix()} "
            "--output outputs/modern_reranker_58_2026-07-16/inference.json"
        ),
    }
    write_json(args.lock, lock)
    print(json.dumps({
        "lock": str(args.lock), "candidates": str(args.candidates),
        "model_revision": revision, "model_manifest_sha256": lock["model"]["manifest_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
