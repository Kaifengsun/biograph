"""Run a portable server-side enrichment pilot for model A/B testing.

This script is intentionally non-destructive. It copies a deterministic subset
of staged raw chunks/tables into a new output directory, runs Step 3 enrichment
there, and writes a small report. It never modifies canonical artifacts,
Neo4j, FAISS, or the full local staging run.
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pharma_doc_pipeline.config import PipelineSettings
from pharma_doc_pipeline.step_03_enrich import (
    C1_C2_THRESHOLD,
    HYDE_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    TABLE_SUMMARY_PROMPT_VERSION,
    ContentEnricher,
)


DEFAULT_SOURCE = Path("data/staging/chunks_2026-06-v2")
DEFAULT_DOCS = [
    "fda_cgmp_guidance",
    "ema_gmp_annex_11",
    "ich_m7_r2",
    "ich_q1a",
    "ich_q2r2",
    "ich_q3c_r9",
    "ich_q3d_r2",
    "ich_q7",
    "ich_q9",
    "ich_q13",
    "ich_q14",
    "who_eml_2023",
    "who_stability_q1f",
]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9._-]+", "_", value)
    return value.strip("_") or "model"


def chunk_score(record: dict) -> tuple:
    """Prefer samples that stress summary, HyDE, short-context, and tables."""
    char_count = int(record.get("char_count") or len(record.get("content", "")))
    line_count = int(record.get("line_count") or 0)
    has_table = bool(record.get("has_table") or record.get("table_refs"))
    summary_eligible = line_count >= 20 or char_count >= 1500
    c2_like = 100 <= char_count <= C1_C2_THRESHOLD
    c1_like = char_count > C1_C2_THRESHOLD
    content = (record.get("heading", "") + " " + record.get("content", "")).lower()
    topic_bonus = int(
        any(
            term in content
            for term in (
                "supplier",
                "stability",
                "impurity",
                "control strategy",
                "risk",
                "shortage",
                "manufacturing",
                "validation",
                "storage condition",
            )
        )
    )
    return (
        int(has_table) * 6
        + int(summary_eligible) * 5
        + int(c2_like) * 4
        + int(c1_like) * 3
        + topic_bonus * 2,
        char_count,
    )


def select_chunks(records: list[dict], limit: int) -> list[dict]:
    if len(records) <= limit:
        return records

    selected_indices: set[int] = set()

    # High-value records by heuristic score.
    ranked = sorted(
        enumerate(records),
        key=lambda item: (chunk_score(item[1]), -item[0]),
        reverse=True,
    )
    for idx, _ in ranked[: max(1, limit // 2)]:
        selected_indices.add(idx)

    # Even coverage across the document so the pilot is not only table-heavy.
    if limit > 1:
        for i in range(limit):
            idx = round(i * (len(records) - 1) / (limit - 1))
            selected_indices.add(idx)
            if len(selected_indices) >= limit:
                break

    # Fill remaining slots with high-score records.
    for idx, _ in ranked:
        if len(selected_indices) >= limit:
            break
        selected_indices.add(idx)

    return [records[i] for i in sorted(selected_indices)[:limit]]


def select_tables(
    table_records: list[dict],
    selected_chunk_ids: set[str],
    limit: int,
) -> list[dict]:
    if not table_records or limit <= 0:
        return []
    selected: list[dict] = []
    seen = set()

    def add(row: dict) -> None:
        key = (row.get("chunk_id"), row.get("table")[:80] if row.get("table") else "")
        if key not in seen and len(selected) < limit:
            clean = dict(row)
            clean.pop("table_summary", None)
            selected.append(clean)
            seen.add(key)

    for row in table_records:
        if row.get("chunk_id") in selected_chunk_ids:
            add(row)

    # Add table-heavy evidence even if the paired chunk was not selected.
    keywords = (
        "storage condition",
        "pde",
        "permitted daily exposure",
        "class 1",
        "validation",
        "essential",
        "scenario",
        "impurity",
    )
    for row in table_records:
        text = (row.get("table") or "").lower()
        if any(term in text for term in keywords):
            add(row)

    for row in table_records:
        add(row)

    return selected


def prepare_pilot_input(
    source_dir: Path,
    output_dir: Path,
    docs: list[str],
    chunks_per_doc: int,
    tables_per_doc: int,
) -> dict:
    if not source_dir.exists():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "_pilot_input_manifest.json"
    if manifest_path.exists():
        return read_json(manifest_path)

    doc_reports = []
    total_chunks = 0
    total_tables = 0

    for doc_id in docs:
        chunk_path = source_dir / f"{doc_id}_chunks.json"
        if not chunk_path.exists():
            raise FileNotFoundError(f"missing chunk file: {chunk_path}")

        raw_chunks = read_json(chunk_path, [])
        selected_chunks = select_chunks(raw_chunks, chunks_per_doc)
        selected_chunk_ids = {
            str(record.get("chunk_id")) for record in selected_chunks if record.get("chunk_id")
        }
        write_json(output_dir / f"{doc_id}_chunks.json", selected_chunks)

        table_path = source_dir / f"{doc_id}_tables.json"
        selected_tables = []
        if table_path.exists():
            selected_tables = select_tables(
                read_json(table_path, []),
                selected_chunk_ids,
                tables_per_doc,
            )
            write_json(output_dir / f"{doc_id}_tables.json", selected_tables)

        doc_reports.append(
            {
                "doc_id": doc_id,
                "source_chunks": len(raw_chunks),
                "pilot_chunks": len(selected_chunks),
                "pilot_tables": len(selected_tables),
            }
        )
        total_chunks += len(selected_chunks)
        total_tables += len(selected_tables)

    manifest = {
        "generated_at": now(),
        "status": "pilot_input_prepared",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "docs": doc_reports,
        "total_chunks": total_chunks,
        "total_tables": total_tables,
        "canonical_artifacts_replaced": False,
        "paid_api_calls": 0,
    }
    write_json(manifest_path, manifest)
    return manifest


def configure_settings(args: argparse.Namespace) -> PipelineSettings:
    settings = PipelineSettings()
    settings.llm.temperature = args.temperature
    settings.llm.timeout = args.timeout
    settings.llm.max_tokens = args.max_tokens

    if args.backend == "ollama":
        settings.llm.backend = "ollama"
        settings.llm.ollama_model = args.model
        settings.llm.ollama_host = args.ollama_host
    else:
        # Any non-ollama backend uses the OpenAI-compatible API path.
        settings.llm.backend = "api"
        settings.llm.api_model = args.model
        settings.llm.api_base_url = args.api_base_url
        if args.api_key_env:
            api_key = os.getenv(args.api_key_env, "")
            if not api_key:
                raise RuntimeError(
                    f"environment variable is empty or missing: {args.api_key_env}"
                )
            settings.llm.api_key = api_key
        else:
            settings.llm.api_key = args.api_key
        api_extra_body = {}
        if args.api_extra_body_json:
            try:
                api_extra_body.update(json.loads(args.api_extra_body_json))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"invalid --api-extra-body-json: {exc}"
                ) from exc
        if args.disable_thinking:
            api_extra_body.setdefault("thinking", {"type": "disabled"})
        if args.disable_qwen_thinking:
            api_extra_body["enable_thinking"] = False
        settings.llm.api_extra_body = api_extra_body

    return settings


def run_pilot(args: argparse.Namespace) -> dict:
    source_dir = Path(args.source)
    output_dir = Path(args.output)
    docs = args.docs or DEFAULT_DOCS

    input_manifest = prepare_pilot_input(
        source_dir=source_dir,
        output_dir=output_dir,
        docs=docs,
        chunks_per_doc=args.chunks_per_doc,
        tables_per_doc=args.tables_per_doc,
    )

    if args.prepare_only:
        return {
            "status": "prepared_only",
            "input_manifest": input_manifest,
        }

    run_report_path = output_dir / "_pilot_run_report.json"
    if run_report_path.exists() and not args.resume:
        raise RuntimeError(
            f"pilot report already exists: {run_report_path}. "
            "Use --resume to skip completed files or choose a new --output."
        )

    settings = configure_settings(args)
    enricher = ContentEnricher(settings=settings)
    enricher.cache_path = output_dir / "_pilot_enrichment_cache.json"
    enricher.cache = enricher._load_cache()

    results = enricher.enrich_all(chunks_dir=output_dir)
    runtime_quality = enricher.get_runtime_quality_report()

    report = {
        "status": "completed_server_enrichment_pilot",
        "generated_at": now(),
        "backend": args.backend,
        "model": args.model,
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "documents": len(results),
        "chunks": sum(len(rows) for rows in results.values()),
        "input_manifest": input_manifest,
        "runtime_quality": runtime_quality,
        "canonical_artifacts_replaced": False,
        "paid_api_calls": 0 if args.backend == "ollama" else "depends_on_local_api",
    }
    write_json(run_report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", required=True)
    parser.add_argument("--backend", choices=["ollama", "api"], default="ollama")
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--api-base-url", default="http://localhost:8000/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--disable-qwen-thinking", action="store_true")
    parser.add_argument("--api-extra-body-json", default="")
    parser.add_argument("--docs", nargs="*", default=None)
    parser.add_argument("--chunks-per-doc", type=int, default=12)
    parser.add_argument("--tables-per-doc", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_pilot(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
