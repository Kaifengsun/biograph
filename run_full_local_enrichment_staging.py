"""Prepare and run a resumable full-corpus local-Ollama enrichment staging job."""

import argparse
import json
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


SOURCE_DIR = Path("data/staging/chunks_2026-06-v2")
OUTPUT_DIR = Path("data/staging/enrichment_full_2026-06-v1")
MODEL = "qwen2.5:14b"
MANIFEST_PATH = OUTPUT_DIR / "_enrichment_manifest.json"
LEGACY_MANIFEST_PATH = OUTPUT_DIR / "_full_enrichment_manifest.json"
RUN_REPORT_PATH = OUTPUT_DIR / "_full_enrichment_run_report.json"
QUALITY_REPORT_PATH = OUTPUT_DIR / "_enrichment_quality_report.json"

EXPECTED_CONTRACT = {
    "documents": 32,
    "chunks": 2478,
    "max_chars_upper_bound": 2271,
    "excluded_doc_ids": ["arxiv_supply_chain"],
    "canonical_artifacts_replaced": False,
    "paid_api_calls": 0,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prompt_versions() -> dict:
    return {
        "summary": SUMMARY_PROMPT_VERSION,
        "hyde": HYDE_PROMPT_VERSION,
        "table_summary": TABLE_SUMMARY_PROMPT_VERSION,
    }


def collect_input_inventory(chunks_dir: Path) -> dict:
    chunk_files = sorted(chunks_dir.glob("*_chunks.json"))
    table_files = sorted(chunks_dir.glob("*_tables.json"))
    enriched_files = sorted(chunks_dir.glob("*_enriched.json"))

    per_document = {}
    total_chunks = 0
    max_chars = 0
    empty_chunks = 0
    document_ids = []

    for path in chunk_files:
        doc_id = path.stem.replace("_chunks", "")
        records = _read_json(path, [])
        document_ids.append(doc_id)
        doc_max = 0
        doc_empty = 0
        for record in records:
            char_count = record.get("char_count")
            if char_count is None:
                char_count = len(record.get("content", ""))
            doc_max = max(doc_max, int(char_count or 0))
            if not str(record.get("content", "")).strip():
                doc_empty += 1
        per_document[doc_id] = {
            "chunks": len(records),
            "max_chars": doc_max,
            "empty_chunks": doc_empty,
        }
        total_chunks += len(records)
        max_chars = max(max_chars, doc_max)
        empty_chunks += doc_empty

    table_rows = 0
    tables_with_summary = 0
    for path in table_files:
        records = _read_json(path, [])
        table_rows += len(records)
        tables_with_summary += sum(1 for row in records if row.get("table_summary"))

    excluded_present = sorted(
        set(document_ids).intersection(EXPECTED_CONTRACT["excluded_doc_ids"])
    )

    return {
        "directory": str(chunks_dir),
        "documents": len(chunk_files),
        "chunks": total_chunks,
        "max_chars": max_chars,
        "empty_chunks": empty_chunks,
        "document_ids": sorted(document_ids),
        "excluded_doc_ids_present": excluded_present,
        "enriched_files": len(enriched_files),
        "tables": {
            "files": len(table_files),
            "rows": table_rows,
            "rows_with_summary": tables_with_summary,
        },
        "per_document": per_document,
    }


def validate_preflight(
    chunks_dir: Path = SOURCE_DIR,
    expected: dict | None = None,
) -> dict:
    expected = expected or EXPECTED_CONTRACT
    inventory = collect_input_inventory(chunks_dir)
    errors = []

    if inventory["documents"] != expected.get("documents"):
        errors.append(
            f"expected {expected.get('documents')} documents, "
            f"found {inventory['documents']}"
        )
    if inventory["chunks"] != expected.get("chunks"):
        errors.append(
            f"expected {expected.get('chunks')} chunks, found {inventory['chunks']}"
        )
    if inventory["max_chars"] > expected.get("max_chars_upper_bound", 10**9):
        errors.append(
            f"max chunk length {inventory['max_chars']} exceeds "
            f"{expected.get('max_chars_upper_bound')}"
        )
    if inventory["empty_chunks"]:
        errors.append(f"found {inventory['empty_chunks']} empty chunks")

    excluded = set(expected.get("excluded_doc_ids", []))
    excluded_present = sorted(set(inventory["document_ids"]).intersection(excluded))
    if excluded_present:
        errors.append(f"excluded doc_id present: {', '.join(excluded_present)}")

    result = {
        "status": "failed" if errors else "passed",
        "checked_at": _now(),
        "expected": expected,
        "actual": {
            "documents": inventory["documents"],
            "chunks": inventory["chunks"],
            "max_chars": inventory["max_chars"],
            "empty_chunks": inventory["empty_chunks"],
            "excluded_doc_ids_present": inventory["excluded_doc_ids_present"],
        },
        "inventory": inventory,
        "errors": errors,
    }
    if errors:
        raise RuntimeError("Preflight failed:\n- " + "\n- ".join(errors))
    return result


def estimate_calls(chunks_dir: Path = SOURCE_DIR) -> dict:
    settings = PipelineSettings()
    records = []
    for path in sorted(chunks_dir.glob("*_chunks.json")):
        records.extend(json.loads(path.read_text(encoding="utf-8")))

    summary_calls = sum(
        record.get("line_count", 0) >= settings.chunking.summary_trigger_lines
        or record.get("char_count", 0) >= settings.chunking.summary_trigger_chars
        for record in records
    )
    hyde_calls = sum(record.get("char_count", 0) >= 100 for record in records)

    eligible_tables = set()
    for path in sorted(chunks_dir.glob("*_tables.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            table = record.get("table", "")
            if len(table) >= 20 and not record.get("table_summary"):
                eligible_tables.add(table)

    table_summary_calls = len(eligible_tables)
    return {
        "documents": len(list(chunks_dir.glob("*_chunks.json"))),
        "chunks": len(records),
        "summary_calls": summary_calls,
        "hyde_calls": hyde_calls,
        "table_summary_calls": table_summary_calls,
        "estimated_total_local_llm_calls": (
            summary_calls + hyde_calls + table_summary_calls
        ),
    }


def write_enrichment_manifest(
    status: str,
    chunks_dir: Path,
    preflight_result: dict | None = None,
    runtime_report: dict | None = None,
    quality_report: dict | None = None,
) -> dict:
    manifest = {
        "manifest_version": "0.2-enrichment-contract",
        "generated_at": _now(),
        "status": status,
        "source_dir": str(SOURCE_DIR),
        "output_dir": str(OUTPUT_DIR),
        "model": MODEL,
        "llm": {
            "backend": "ollama",
            "model": MODEL,
        },
        "prompt_versions": _prompt_versions(),
        "c1_c2_threshold_chars": C1_C2_THRESHOLD,
        "corpus_contract": EXPECTED_CONTRACT,
        "input_inventory": collect_input_inventory(chunks_dir),
        "estimate": estimate_calls(chunks_dir),
        "preflight": preflight_result,
        "runtime_report": runtime_report,
        "quality_report_path": str(QUALITY_REPORT_PATH) if quality_report else None,
        "canonical_artifacts_replaced": False,
        "paid_api_calls": 0,
        "resume_supported": True,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(MANIFEST_PATH, manifest)
    _write_json(LEGACY_MANIFEST_PATH, manifest)
    return manifest


def build_quality_report(
    chunks_dir: Path = OUTPUT_DIR,
    runtime_quality: dict | None = None,
) -> dict:
    settings = PipelineSettings()
    raw_inventory = collect_input_inventory(chunks_dir)
    enriched_files = sorted(chunks_dir.glob("*_enriched.json"))

    counters = {
        "enriched_documents": len(enriched_files),
        "enriched_chunks": 0,
        "chunks_with_enrichment_meta": 0,
        "summary_eligible_chunks": 0,
        "summary_generated_chunks": 0,
        "hyde_eligible_chunks": 0,
        "hyde_generated_chunks": 0,
        "hyde_questions_generated": 0,
        "hyde_c1_chunks": 0,
        "hyde_c2_chunks": 0,
        "unsupported_named_reference_questions_filtered": 0,
    }
    per_document = {}

    for path in enriched_files:
        doc_id = path.stem.replace("_enriched", "")
        records = _read_json(path, [])
        doc_counter = {
            "chunks": len(records),
            "chunks_with_enrichment_meta": 0,
            "summary_generated_chunks": 0,
            "hyde_generated_chunks": 0,
            "hyde_questions_generated": 0,
            "hyde_c1_chunks": 0,
            "hyde_c2_chunks": 0,
        }
        for record in records:
            meta = record.get("enrichment_meta") or {}
            counters["enriched_chunks"] += 1
            if meta:
                counters["chunks_with_enrichment_meta"] += 1
                doc_counter["chunks_with_enrichment_meta"] += 1

            char_count = record.get("char_count")
            if char_count is None:
                char_count = len(record.get("content", ""))
            summary_eligible = meta.get(
                "summary_eligible",
                record.get("line_count", 0) >= settings.chunking.summary_trigger_lines
                or int(char_count or 0) >= settings.chunking.summary_trigger_chars,
            )
            hyde_eligible = meta.get(
                "hyde_eligible",
                settings.chunking.enable_hyde and int(char_count or 0) >= 100,
            )
            if summary_eligible:
                counters["summary_eligible_chunks"] += 1
            if record.get("summary"):
                counters["summary_generated_chunks"] += 1
                doc_counter["summary_generated_chunks"] += 1
            if hyde_eligible:
                counters["hyde_eligible_chunks"] += 1
            if record.get("hyde_questions"):
                counters["hyde_generated_chunks"] += 1
                doc_counter["hyde_generated_chunks"] += 1
                question_count = len(record.get("hyde_questions") or [])
                counters["hyde_questions_generated"] += question_count
                doc_counter["hyde_questions_generated"] += question_count

            strategy = meta.get("hyde_strategy") or record.get("hyde_strategy")
            if strategy == "C1":
                counters["hyde_c1_chunks"] += 1
                doc_counter["hyde_c1_chunks"] += 1
            elif strategy == "C2":
                counters["hyde_c2_chunks"] += 1
                doc_counter["hyde_c2_chunks"] += 1

            source_grounding = meta.get("source_grounding") or {}
            filtered = int(
                source_grounding.get(
                    "unsupported_named_reference_questions_filtered",
                    0,
                )
                or 0
            )
            counters[
                "unsupported_named_reference_questions_filtered"
            ] += filtered

        per_document[doc_id] = doc_counter

    table_rows = raw_inventory["tables"]["rows"]
    tables_with_summary = raw_inventory["tables"]["rows_with_summary"]
    status = (
        "complete_enriched_artifacts"
        if raw_inventory["chunks"] and counters["enriched_chunks"] == raw_inventory["chunks"]
        else "partial_or_not_started"
    )
    return {
        "report_version": "0.1-enrichment-quality",
        "generated_at": _now(),
        "status": status,
        "raw_inventory": raw_inventory,
        "prompt_versions": _prompt_versions(),
        "c1_c2_threshold_chars": C1_C2_THRESHOLD,
        "artifact_counters": counters,
        "table_summary": {
            "table_rows": table_rows,
            "rows_with_summary": tables_with_summary,
            "coverage": (
                round(tables_with_summary / table_rows, 4) if table_rows else 0.0
            ),
        },
        "runtime_quality": runtime_quality or {},
        "per_document": per_document,
    }


def prepare_workspace() -> dict:
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Refusing to overwrite existing staging directory: {OUTPUT_DIR}")

    source_preflight = validate_preflight(SOURCE_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    copied_files = []
    for pattern in ("*_chunks.json", "*_tables.json"):
        for source_path in sorted(SOURCE_DIR.glob(pattern)):
            output_path = OUTPUT_DIR / source_path.name
            shutil.copy2(source_path, output_path)
            copied_files.append(output_path.name)

    output_preflight = validate_preflight(OUTPUT_DIR)
    manifest = write_enrichment_manifest(
        "prepared_full_local_enrichment_staging",
        chunks_dir=OUTPUT_DIR,
        preflight_result={
            "source": source_preflight,
            "output": output_preflight,
        },
    )
    manifest["copied_files"] = len(copied_files)
    _write_json(MANIFEST_PATH, manifest)
    _write_json(LEGACY_MANIFEST_PATH, manifest)
    return manifest


def preflight_only() -> dict:
    chunks_dir = OUTPUT_DIR if OUTPUT_DIR.exists() else SOURCE_DIR
    preflight_result = validate_preflight(chunks_dir)
    quality_report = build_quality_report(chunks_dir=chunks_dir)
    _write_json(QUALITY_REPORT_PATH, quality_report)
    return write_enrichment_manifest(
        "preflight_passed_full_local_enrichment_staging",
        chunks_dir=chunks_dir,
        preflight_result=preflight_result,
        quality_report=quality_report,
    )


def run_local() -> dict:
    if not (MANIFEST_PATH.exists() or LEGACY_MANIFEST_PATH.exists()):
        raise RuntimeError("Prepare the full enrichment staging workspace before running")
    if RUN_REPORT_PATH.exists():
        raise RuntimeError(f"Refusing to rerun a completed staging job: {OUTPUT_DIR}")

    preflight_result = validate_preflight(OUTPUT_DIR)
    write_enrichment_manifest(
        "running_full_local_enrichment_staging",
        chunks_dir=OUTPUT_DIR,
        preflight_result=preflight_result,
    )

    settings = PipelineSettings()
    settings.llm.backend = "ollama"
    settings.llm.ollama_model = MODEL

    enricher = ContentEnricher(settings=settings)
    enricher.cache_path = OUTPUT_DIR / "_full_enrichment_cache.json"
    enricher.cache = enricher._load_cache()
    results = enricher.enrich_all(chunks_dir=OUTPUT_DIR)
    runtime_quality = enricher.get_runtime_quality_report()
    quality_report = build_quality_report(
        chunks_dir=OUTPUT_DIR,
        runtime_quality=runtime_quality,
    )
    _write_json(QUALITY_REPORT_PATH, quality_report)

    report = {
        "status": "completed_full_local_enrichment_staging",
        "model": MODEL,
        "documents": len(results),
        "chunks": sum(len(records) for records in results.values()),
        "new_local_llm_calls_this_run": enricher._call_count,
        "paid_api_calls": 0,
        "canonical_artifacts_replaced": False,
        "manifest_path": str(MANIFEST_PATH),
        "quality_report_path": str(QUALITY_REPORT_PATH),
    }
    _write_json(RUN_REPORT_PATH, report)
    write_enrichment_manifest(
        "completed_full_local_enrichment_staging",
        chunks_dir=OUTPUT_DIR,
        preflight_result=preflight_result,
        runtime_report=report,
        quality_report=quality_report,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run-local", action="store_true")
    args = parser.parse_args()

    if sum((args.estimate, args.preflight, args.prepare, args.run_local)) != 1:
        raise SystemExit(
            "Choose exactly one of --estimate, --preflight, --prepare, or --run-local"
        )

    if args.estimate:
        result = estimate_calls()
    elif args.preflight:
        result = preflight_only()
    elif args.prepare:
        result = prepare_workspace()
    else:
        result = run_local()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
