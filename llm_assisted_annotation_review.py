"""Checkpointed LLM-assisted review of source-evidence candidates.

The output is an annotation aid. It never promotes a row to formal gold-label
status and refuses model-selected IDs that are absent from the provided source
blocks.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_CORPUS = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
PROMPT_VERSION = "v1_candidate_only_source_grounded"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def load_chunk_store(corpus: Path) -> dict[str, dict[str, Any]]:
    store = {}
    for path in sorted(corpus.glob("*_enriched.json")):
        for row in read_json(path):
            chunk_id = str(row.get("chunk_id", ""))
            if chunk_id:
                store[chunk_id] = row
    return store


def prompt_for(row: dict[str, Any], store: dict[str, dict[str, Any]], max_chunks: int = 8) -> tuple[str, list[str]]:
    candidate_ids = list(row.get("candidate_evidence_chunk_ids") or [])[:max_chunks]
    blocks = []
    present_ids = []
    for chunk_id in candidate_ids:
        chunk = store.get(chunk_id)
        if not chunk:
            continue
        present_ids.append(chunk_id)
        text = str(chunk.get("content", ""))[:1600]
        blocks.append(f"[CHUNK_ID: {chunk_id}]\nDocument: {chunk.get('doc_id', '')}\nHeading: {chunk.get('heading', '')}\n{text}")
    prompt = f"""You are assisting evidence annotation for a pharmaceutical regulatory retrieval study.

Question: {row['query']}

Select at most three provided CHUNK_ID values that directly support an answer to the question. A chunk is direct support only when its text contains the relevant requirement, definition, condition, table value, or explicit relation. Do not infer facts from general topic similarity. If no supplied chunk directly supports the answer, select none and set insufficient_evidence to true.

Return exactly one JSON object with this schema:
{{"direct_support_chunk_ids":["..."],"insufficient_evidence":true|false,"rationale":"brief source-grounded rationale"}}

Only select these IDs: {present_ids}

Candidate source blocks:
{chr(10).join(blocks)}"""
    return prompt, present_ids


def call_api(session: requests.Session, api_key: str, model: str, prompt: str, timeout: int) -> str:
    response = session.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.0,
            "max_tokens": 300,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return str(response.json()["choices"][0]["message"]["content"])


def parse_review(raw: str, allowed_ids: list[str]) -> dict[str, Any]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
        candidate = candidate.rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            return {"direct_support_chunk_ids": [], "insufficient_evidence": True, "rationale": "model_output_not_valid_json", "output_valid": False}
        try:
            payload, _end = json.JSONDecoder().raw_decode(candidate[start:])
        except json.JSONDecodeError:
            return {"direct_support_chunk_ids": [], "insufficient_evidence": True, "rationale": "model_output_not_valid_json", "output_valid": False}
    selected = [str(chunk_id) for chunk_id in payload.get("direct_support_chunk_ids", []) if str(chunk_id) in allowed_ids]
    return {
        "direct_support_chunk_ids": selected[:3],
        "insufficient_evidence": bool(payload.get("insufficient_evidence", not selected)),
        "rationale": str(payload.get("rationale", ""))[:1000],
        "output_valid": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-assisted candidate evidence review")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    output = Path(args.output)
    results_path = output / "llm_assisted_reviews.jsonl"
    if output.exists() and not args.resume:
        raise RuntimeError(f"refusing to overwrite existing review output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing")
    rows = [row for row in read_json(Path(args.pack))["queries"] if row.get("review_status") != "excluded"]
    if args.limit:
        rows = rows[:args.limit]
    store = load_chunk_store(Path(args.corpus))
    existing = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line] if results_path.exists() else []
    completed = {row["annotation_id"] for row in existing}
    session = requests.Session()
    new_calls = 0
    for row in rows:
        annotation_id = row["annotation_id"]
        if annotation_id in completed:
            continue
        prompt, allowed_ids = prompt_for(row, store)
        if not allowed_ids:
            result = {"annotation_id": annotation_id, "review": {"direct_support_chunk_ids": [], "insufficient_evidence": True, "rationale": "no_available_candidate_source_chunks", "output_valid": True}}
        else:
            raw = call_api(session, api_key, args.model, prompt, args.timeout)
            result = {"annotation_id": annotation_id, "review": parse_review(raw, allowed_ids), "raw_model_output": raw}
            new_calls += 1
        result.update({"model": args.model, "prompt_version": PROMPT_VERSION, "formal_gold_label": False})
        existing.append(result)
        if new_calls and new_calls % 5 == 0:
            write_jsonl(results_path, existing)
    write_jsonl(results_path, existing)
    write_json(output / "review_run_report.json", {
        "pack": args.pack, "model": args.model, "prompt_version": PROMPT_VERSION,
        "records": len(existing), "new_api_calls": new_calls, "formal_gold_labels_created": False,
    })
    print(json.dumps({"records": len(existing), "new_api_calls": new_calls, "formal_gold_labels_created": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
