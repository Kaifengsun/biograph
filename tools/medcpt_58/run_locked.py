"""Run locked MedCPT full-corpus dense retrieval and BM25 top-50 cross reranking."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

from tools.medcpt_58.common import ROOT, rank_scores, read_json, sha256_file
from tools.medcpt_58.validate_lock import validate_lock


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def encode_cls(model, tokenizer, texts, *, max_length: int, batch_size: int, device: str) -> np.ndarray:
    rows = []
    for offset in range(0, len(texts), batch_size):
        batch = texts[offset:offset + batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        ).to(device)
        with torch.inference_mode():
            rows.append(model(**encoded).last_hidden_state[:, 0, :].cpu().numpy())
    return np.concatenate(rows, axis=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    lock = read_json(args.lock)
    report = validate_lock(lock, args.lock)
    if not report["passed"]:
        raise RuntimeError(f"lock validation failed: {report['checks']}")
    device = lock["inference"]["device"]
    pack = read_json(ROOT / lock["inputs"]["pack_path"])
    dense = read_json(ROOT / lock["inputs"]["dense_corpus_path"])
    bm25 = read_json(ROOT / lock["inputs"]["bm25_candidates_path"])
    started = time.perf_counter()

    query_spec = lock["models"]["query"]
    article_spec = lock["models"]["article"]
    query_path = ROOT / query_spec["local_path"]
    article_path = ROOT / article_spec["local_path"]
    query_tokenizer = AutoTokenizer.from_pretrained(query_path, local_files_only=True)
    article_tokenizer = AutoTokenizer.from_pretrained(article_path, local_files_only=True)
    query_model = AutoModel.from_pretrained(query_path, local_files_only=True).to(device).eval()
    article_model = AutoModel.from_pretrained(article_path, local_files_only=True).to(device).eval()
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)

    article_rows = dense["records"]
    article_embeddings = encode_cls(
        article_model,
        article_tokenizer,
        [row["article_pair"] for row in article_rows],
        max_length=lock["inference"]["dual_encoder"]["article_max_length"],
        batch_size=lock["inference"]["dual_encoder"]["article_batch_size"],
        device=device,
    )
    query_embeddings = encode_cls(
        query_model,
        query_tokenizer,
        [row["query"] for row in pack["queries"]],
        max_length=lock["inference"]["dual_encoder"]["query_max_length"],
        batch_size=lock["inference"]["dual_encoder"]["query_batch_size"],
        device=device,
    )
    del article_model, query_model
    torch.cuda.empty_cache()
    dense_scores = query_embeddings @ article_embeddings.T
    chunk_ids = [row["chunk_id"] for row in article_rows]
    dense_by_id = {
        query["annotation_id"]: rank_scores(chunk_ids, dense_scores[index])
        for index, query in enumerate(pack["queries"])
    }
    print("MedCPT dual-encoder complete", flush=True)

    cross_spec = lock["models"]["cross"]
    cross_path = ROOT / cross_spec["local_path"]
    cross_tokenizer = AutoTokenizer.from_pretrained(cross_path, local_files_only=True)
    cross_model = AutoModelForSequenceClassification.from_pretrained(
        cross_path, local_files_only=True
    ).to(device).eval()
    cross_by_id = {}
    bm25_rows = {row["annotation_id"]: row for row in bm25["queries"]}
    for query_index, query in enumerate(pack["queries"], 1):
        source = bm25_rows[query["annotation_id"]]
        scored = []
        batch_size = lock["inference"]["cross_encoder"]["batch_size"]
        for offset in range(0, len(source["candidates"]), batch_size):
            batch = source["candidates"][offset:offset + batch_size]
            pairs = [[query["query"], row["passage"]] for row in batch]
            encoded = cross_tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=lock["inference"]["cross_encoder"]["max_length"],
                return_tensors="pt",
            ).to(device)
            with torch.inference_mode():
                scores = cross_model(**encoded).logits.squeeze(dim=1).cpu().numpy()
            scored.extend(
                {"chunk_id": row["chunk_id"], "score": float(score)}
                for row, score in zip(batch, scores, strict=True)
            )
        ranked = sorted(scored, key=lambda row: (-row["score"], row["chunk_id"]))
        cross_by_id[query["annotation_id"]] = [
            dict(row, rank=rank) for rank, row in enumerate(ranked, 1)
        ]
        print(f"MedCPT cross-encoder [{query_index}/58] {query['annotation_id']}", flush=True)

    payload = {
        "schema_version": "1.0",
        "status": "complete",
        "evaluation_role": lock["evaluation"]["role"],
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "lock_sha256": sha256_file(args.lock),
        "runtime_seconds": time.perf_counter() - started,
        "queries": [
            {
                "annotation_id": row["annotation_id"],
                "query_slice": row["query_slice"],
                "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
                "medcpt_dual_encoder_ranking": dense_by_id[row["annotation_id"]],
                "medcpt_cross_encoder_ranking": cross_by_id[row["annotation_id"]],
            }
            for row in pack["queries"]
        ],
    }
    atomic_write(args.output, payload)
    print(json.dumps({"output": str(args.output), "runtime_seconds": payload["runtime_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
