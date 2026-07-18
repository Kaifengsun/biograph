"""Freeze MedCPT inputs, exact model revisions, inference rules, and code hashes."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import transformers

from tools.medcpt_58.common import (
    ARTICLE_MAX_LENGTH,
    ARTICLE_MODEL_ID,
    ARTICLE_REVISION,
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    CANDIDATE_DEPTH,
    CORPUS_DEPTH,
    CROSS_MAX_LENGTH,
    CROSS_MODEL_ID,
    CROSS_REVISION,
    DEFAULT_BM25_CANDIDATES,
    DEFAULT_CORPUS,
    DEFAULT_PACK,
    METRICS,
    QUERY_MAX_LENGTH,
    QUERY_MODEL_ID,
    QUERY_REVISION,
    ROOT,
    corpus_manifest,
    prepare_dense_corpus,
    runtime_model_manifest,
    sha256_file,
    sha256_json,
    write_json,
)


CODE_FILES = (
    "tools/medcpt_58/common.py",
    "tools/medcpt_58/prepare_lock.py",
    "tools/medcpt_58/validate_lock.py",
    "tools/medcpt_58/run_locked.py",
    "tools/medcpt_58/evaluate.py",
)


def model_record(model_id: str, revision: str, path: Path) -> dict:
    files = runtime_model_manifest(path)
    return {
        "id": model_id,
        "revision": revision,
        "source": "official_ncbi_huggingface_repository_via_hf_mirror",
        "source_url": f"https://huggingface.co/{model_id}/tree/{revision}",
        "local_path": path.resolve().relative_to(ROOT).as_posix(),
        "license": "public-domain",
        "files": files,
        "manifest_sha256": sha256_json(files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--bm25-candidates", type=Path, default=DEFAULT_BM25_CANDIDATES)
    parser.add_argument("--query-model-dir", required=True, type=Path)
    parser.add_argument("--article-model-dir", required=True, type=Path)
    parser.add_argument("--cross-model-dir", required=True, type=Path)
    parser.add_argument("--dense-corpus", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--article-batch-size", type=int, default=16)
    parser.add_argument("--query-batch-size", type=int, default=32)
    parser.add_argument("--cross-batch-size", type=int, default=8)
    args = parser.parse_args()
    if args.dense_corpus.exists() or args.lock.exists():
        raise FileExistsError("dense corpus and lock outputs must not already exist")

    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    bm25 = json.loads(args.bm25_candidates.read_text(encoding="utf-8"))
    if len(pack.get("queries", [])) != 58 or len(bm25.get("queries", [])) != 58:
        raise ValueError("formal pack and BM25 candidate file must each contain 58 queries")
    dense_corpus = prepare_dense_corpus(args.corpus)
    write_json(args.dense_corpus, dense_corpus)

    models = {
        "query": model_record(QUERY_MODEL_ID, QUERY_REVISION, args.query_model_dir),
        "article": model_record(ARTICLE_MODEL_ID, ARTICLE_REVISION, args.article_model_dir),
        "cross": model_record(CROSS_MODEL_ID, CROSS_REVISION, args.cross_model_dir),
    }
    lock = {
        "schema_version": "1.0",
        "status": "locked_before_feedback_motivated_medcpt_scores",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "results_observed_at_lock": False,
        "one_shot_reporting_rule": True,
        "models": models,
        "inputs": {
            "pack_path": args.pack.resolve().relative_to(ROOT).as_posix(),
            "pack_sha256": sha256_file(args.pack),
            "corpus_path": args.corpus.resolve().relative_to(ROOT).as_posix(),
            "corpus_manifest_sha256": sha256_json(corpus_manifest(args.corpus)),
            "bm25_candidates_path": args.bm25_candidates.resolve().relative_to(ROOT).as_posix(),
            "bm25_candidates_sha256": sha256_file(args.bm25_candidates),
            "dense_corpus_path": args.dense_corpus.resolve().relative_to(ROOT).as_posix(),
            "dense_corpus_sha256": sha256_file(args.dense_corpus),
        },
        "inference": {
            "dual_encoder": {
                "corpus_depth": CORPUS_DEPTH,
                "query_max_length": QUERY_MAX_LENGTH,
                "article_max_length": ARTICLE_MAX_LENGTH,
                "representations": "last_hidden_state_cls",
                "similarity": "unnormalized_dot_product",
                "article_input": "[parents_context + heading, content]",
                "query_batch_size": args.query_batch_size,
                "article_batch_size": args.article_batch_size,
            },
            "cross_encoder": {
                "candidate_source": "frozen_bm25_top50",
                "candidate_depth": CANDIDATE_DEPTH,
                "max_length": CROSS_MAX_LENGTH,
                "input": "[query, parents_context + heading + content]",
                "score": "single_relevance_logit",
                "batch_size": args.cross_batch_size,
            },
            "device": "cuda:0",
            "precision": "float32",
            "fine_tuning": False,
            "unicode_normalization": "NFC",
            "tie_break": "score_desc_then_chunk_id_asc",
        },
        "evaluation": {
            "role": "feedback_motivated_locked_extension",
            "query_count": 58,
            "metrics": list(METRICS),
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "gain": "binary",
            "resampling_unit": "query",
            "report_all_methods_and_slices": True,
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
    }
    write_json(args.lock, lock)
    print(json.dumps({
        "lock": str(args.lock),
        "dense_corpus": str(args.dense_corpus),
        "model_manifests": {name: row["manifest_sha256"] for name, row in models.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
