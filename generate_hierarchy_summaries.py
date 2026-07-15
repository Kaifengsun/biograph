"""Generate checkpointed source-grounded summaries for graph hierarchy nodes."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_INPUT = Path(
    "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build1/hierarchy_summary_inputs"
)
PROMPT_VERSION = "v1_hierarchy_source_grounded"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def prompt_for(record: dict[str, Any], generated: dict[str, str]) -> str:
    source_blocks: list[str] = []
    for unit in record["source_units"]:
        text = unit.get("source_text") or ""
        dependency = unit.get("depends_on")
        if dependency:
            text = generated.get(dependency, "")
        if not text:
            continue
        source_blocks.append(
            f"[Source ID: {unit['source_id']} | Heading: {unit.get('heading', '')}]\n{text}"
        )
    return f"""You are preparing a source-grounded {'document' if record['summary_type'] == 'document' else 'section'} overview from a pharmaceutical regulatory document.

Title: {record['heading']}
Document ID: {record['doc_id']}

Write a concise 2-4 sentence overview that states only the scope, requirements, conditions, thresholds, or definitions explicitly supported by the source blocks. Preserve uncertainty: do not invent supply-chain impacts, enforcement outcomes, regulations, entities, or numeric values. Do not cite a source that is absent from the blocks. If the source blocks are insufficient for a meaningful regulatory overview, return exactly [INSUFFICIENT_SOURCE].

Source blocks:
{chr(10).join(source_blocks)}"""


def call_api(
    session: requests.Session,
    api_base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: int,
) -> str:
    url = api_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 600,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt}],
    }
    response = session.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return " ".join(str(content).split())


def call_with_retries(
    session: requests.Session,
    api_base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: int,
    retries: int,
) -> str:
    last_error: requests.RequestException | None = None
    for attempt in range(retries + 1):
        try:
            return call_api(session, api_base_url, api_key, model, prompt, timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(min(2 ** attempt, 8))
    raise last_error if last_error else RuntimeError("unexpected API retry state")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate source-grounded hierarchy summaries")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    records = read_jsonl(input_dir / "hierarchy_summary_inputs.jsonl")
    input_report = json.loads((input_dir / "hierarchy_summary_input_report.json").read_text(encoding="utf-8"))
    if args.dry_run:
        print(json.dumps({
            "status": "dry_run_no_api_calls",
            "input_records": len(records),
            "expected_api_calls": input_report["expected_llm_calls"],
            "model": args.model,
            "prompt_version": PROMPT_VERSION,
        }, ensure_ascii=False, indent=2))
        return

    results_path = output_dir / "hierarchy_summaries.jsonl"
    if output_dir.exists() and not args.resume:
        raise RuntimeError(f"refusing to overwrite existing output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(results_path) if results_path.exists() else []
    generated = {row["summary_id"]: row["summary"] for row in existing}
    session = requests.Session()
    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"environment variable is empty or missing: {args.api_key_env}")

    started = time.time()
    new_calls = 0
    for index, record in enumerate(records, 1):
        summary_id = record["summary_id"]
        if summary_id in generated:
            continue
        prompt = prompt_for(record, generated)
        try:
            summary = call_with_retries(
                session, args.api_base_url, api_key, args.model, prompt,
                args.timeout, args.retries,
            )
        except requests.RequestException as exc:
            write_jsonl(results_path, existing)
            raise RuntimeError(f"API call failed for {summary_id}; resume is supported") from exc
        result = {
            "summary_id": summary_id,
            "summary_type": record["summary_type"],
            "target_node_id": record["target_node_id"],
            "doc_id": record["doc_id"],
            "heading": record["heading"],
            "summary": summary,
            "source_ids": [unit["source_id"] for unit in record["source_units"]],
            "omitted_source_ids": record["omitted_source_ids"],
            "model": args.model,
            "prompt_version": PROMPT_VERSION,
        }
        existing.append(result)
        generated[summary_id] = summary
        new_calls += 1
        if new_calls % 10 == 0:
            write_jsonl(results_path, existing)
            print(f"Generated {len(existing)}/{len(records)} hierarchy summaries")

    write_jsonl(results_path, existing)
    report = {
        "status": "completed",
        "input": str(input_dir),
        "output": str(output_dir),
        "model": args.model,
        "prompt_version": PROMPT_VERSION,
        "records": len(records),
        "new_api_calls": new_calls,
        "retries_per_call": args.retries,
        "elapsed_seconds": round(time.time() - started, 2),
        "canonical_artifacts_replaced": False,
    }
    write_json(output_dir / "hierarchy_summary_run_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
