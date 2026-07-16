"""Execute the exact locked Qwen3 reranker over frozen BM25 candidates."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from huggingface_hub import snapshot_download
from transformers import AutoModelForCausalLM, AutoTokenizer

from tools.modern_reranker_58.common import ROOT, rank_scored_candidates, read_json, sha256_file
from tools.modern_reranker_58.validate_lock import validate_lock


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    lock = read_json(args.lock)
    lock_report = validate_lock(lock, args.lock)
    if not lock_report["passed"]:
        raise RuntimeError(f"lock validation failed: {lock_report['checks']}")
    candidates_path = ROOT / lock["inputs"]["candidates_path"]
    candidates = read_json(candidates_path)
    lock_hash = sha256_file(args.lock)

    completed: dict[str, dict] = {}
    if args.output.exists():
        checkpoint = read_json(args.output)
        if checkpoint.get("lock_sha256") != lock_hash:
            raise RuntimeError("existing checkpoint belongs to another lock")
        completed = {row["annotation_id"]: row for row in checkpoint.get("queries", [])}

    snapshot = Path(snapshot_download(
        lock["model"]["id"], revision=lock["model"]["revision"], local_files_only=True,
    ))
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, padding_side="left",
    )
    tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        snapshot, local_files_only=True, torch_dtype=torch.bfloat16,
    ).to(lock["inference"]["device"])
    model.eval()
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.use_deterministic_algorithms(True)

    false_token_id = tokenizer.convert_tokens_to_ids("no")
    true_token_id = tokenizer.convert_tokens_to_ids("yes")
    if false_token_id == tokenizer.unk_token_id or true_token_id == tokenizer.unk_token_id:
        raise RuntimeError("Qwen3 yes/no scoring tokens are unavailable")
    prefix = (
        '<|im_start|>system\nJudge whether the Document meets the requirements based on the '
        'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
        '<|im_end|>\n<|im_start|>user\n'
    )
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
    suffix_tokens = tokenizer.encode(suffix, add_special_tokens=False)
    content_max_length = lock["inference"]["max_length"] - len(prefix_tokens) - len(suffix_tokens)
    if content_max_length <= 0:
        raise RuntimeError("locked max length cannot contain the official reranker prompt")

    started = time.perf_counter()
    for query_index, query_row in enumerate(candidates["queries"], 1):
        annotation_id = query_row["annotation_id"]
        if annotation_id in completed:
            continue
        scored: list[dict] = []
        batch_size = lock["inference"]["batch_size"]
        for offset in range(0, len(query_row["candidates"]), batch_size):
            batch = query_row["candidates"][offset:offset + batch_size]
            formatted = [
                f"<Instruct>: {lock['inference']['task_instruction']}\n"
                f"<Query>: {query_row['query']}\n<Document>: {row['passage']}"
                for row in batch
            ]
            encoded = tokenizer(
                formatted, padding=False, truncation=True,
                max_length=content_max_length, add_special_tokens=False,
            )
            model_inputs = []
            for token_ids in encoded["input_ids"]:
                ids = prefix_tokens + token_ids + suffix_tokens
                model_inputs.append({"input_ids": ids, "attention_mask": [1] * len(ids)})
            inputs = tokenizer.pad(model_inputs, padding=True, return_tensors="pt").to(model.device)
            with torch.inference_mode():
                hidden = model.model(**inputs, return_dict=True).last_hidden_state[:, -1, :]
                logits = model.get_output_embeddings()(hidden).float()
                binary_logits = torch.stack(
                    [logits[:, false_token_id], logits[:, true_token_id]], dim=1,
                )
                scores = torch.softmax(binary_logits, dim=1)[:, 1].cpu().tolist()
            scored.extend(
                {"chunk_id": row["chunk_id"], "bm25_rank": row["bm25_rank"], "score": score}
                for row, score in zip(batch, scores, strict=True)
            )
        completed[annotation_id] = {
            "annotation_id": annotation_id,
            "query_slice": query_row["query_slice"],
            "gold_evidence_chunk_ids": query_row["gold_evidence_chunk_ids"],
            "ranking": rank_scored_candidates(scored),
        }
        payload = {
            "schema_version": "1.0",
            "status": "checkpoint" if query_index < len(candidates["queries"]) else "complete",
            "evaluation_role": "supplementary_posthoc",
            "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "lock_sha256": lock_hash,
            "model_id": lock["model"]["id"],
            "model_revision": lock["model"]["revision"],
            "queries": [completed[row["annotation_id"]] for row in candidates["queries"] if row["annotation_id"] in completed],
            "runtime_seconds": time.perf_counter() - started,
        }
        atomic_write(args.output, payload)
        print(f"[{len(completed)}/58] {annotation_id}", flush=True)


if __name__ == "__main__":
    main()
