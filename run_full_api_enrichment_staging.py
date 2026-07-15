"""Run a non-destructive full-corpus enrichment job with web API models.

The script copies the staged chunk/table corpus into a new output directory,
runs Step 3 enrichment there, and writes manifest/run/quality reports. It never
modifies canonical artifacts, Neo4j, vector indexes, or earlier enrichment runs.
"""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from pharma_doc_pipeline.config import PipelineSettings
from pharma_doc_pipeline.step_03_enrich import (
    C1_C2_THRESHOLD,
    HYDE_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    TABLE_SUMMARY_PROMPT_VERSION,
    ContentEnricher,
)
from run_full_local_enrichment_staging import (
    EXPECTED_CONTRACT,
    build_quality_report,
    collect_input_inventory,
    estimate_calls,
    validate_preflight,
)


DEFAULT_SOURCE = Path("data/staging/chunks_2026-06-v2")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prompt_versions() -> Dict[str, str]:
    return {
        "summary": SUMMARY_PROMPT_VERSION,
        "hyde": HYDE_PROMPT_VERSION,
        "table_summary": TABLE_SUMMARY_PROMPT_VERSION,
    }


def build_manifest(
    status: str,
    args: argparse.Namespace,
    preflight_result: Dict[str, Any] | None = None,
    runtime_report: Dict[str, Any] | None = None,
    quality_report: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source_dir = Path(args.source)
    output_dir = Path(args.output)
    manifest = {
        "manifest_version": "0.3-full-api-enrichment",
        "generated_at": now(),
        "status": status,
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "model": args.model,
        "llm": {
            "backend": "api",
            "model": args.model,
            "api_base_url": args.api_base_url,
            "disable_thinking": bool(args.disable_thinking),
            "disable_qwen_thinking": bool(args.disable_qwen_thinking),
        },
        "prompt_versions": prompt_versions(),
        "c1_c2_threshold_chars": C1_C2_THRESHOLD,
        "corpus_contract": EXPECTED_CONTRACT,
        "input_inventory": collect_input_inventory(output_dir),
        "estimate": estimate_calls(output_dir),
        "preflight": preflight_result,
        "runtime_report": runtime_report,
        "quality_report_path": (
            str(output_dir / "_enrichment_quality_report.json")
            if quality_report
            else None
        ),
        "canonical_artifacts_replaced": False,
        "paid_api_calls": "external_api",
        "resume_supported": True,
    }
    write_json(output_dir / "_enrichment_manifest.json", manifest)
    return manifest


def prepare_workspace(args: argparse.Namespace) -> Dict[str, Any]:
    source_dir = Path(args.source)
    output_dir = Path(args.output)
    manifest_path = output_dir / "_enrichment_manifest.json"

    if output_dir.exists():
        if args.resume and manifest_path.exists():
            return build_manifest("prepared_existing_resume", args)
        raise RuntimeError(
            f"refusing to use existing output directory without --resume: {output_dir}"
        )

    source_preflight = validate_preflight(source_dir)
    output_dir.mkdir(parents=True)
    copied_files = []
    for pattern in ("*_chunks.json", "*_tables.json"):
        for source_path in sorted(source_dir.glob(pattern)):
            output_path = output_dir / source_path.name
            shutil.copy2(source_path, output_path)
            copied_files.append(output_path.name)

    output_preflight = validate_preflight(output_dir)
    manifest = build_manifest(
        "prepared_full_api_enrichment_staging",
        args,
        preflight_result={
            "source": source_preflight,
            "output": output_preflight,
        },
    )
    manifest["copied_files"] = len(copied_files)
    write_json(manifest_path, manifest)
    return manifest


def configure_settings(args: argparse.Namespace) -> PipelineSettings:
    settings = PipelineSettings()
    settings.llm.backend = "api"
    settings.llm.api_model = args.model
    settings.llm.api_base_url = args.api_base_url
    settings.llm.temperature = args.temperature
    settings.llm.max_tokens = args.max_tokens
    settings.llm.timeout = args.timeout

    api_key = os.getenv(args.api_key_env, "")
    if not api_key:
        raise RuntimeError(
            f"environment variable is empty or missing: {args.api_key_env}"
        )
    settings.llm.api_key = api_key

    api_extra_body: Dict[str, Any] = {}
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


def run_api(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output)
    run_report_path = output_dir / "_full_enrichment_run_report.json"
    quality_report_path = output_dir / "_enrichment_quality_report.json"

    if not output_dir.exists():
        prepare_workspace(args)
    if run_report_path.exists() and not args.resume:
        raise RuntimeError(
            f"refusing to rerun completed full job: {run_report_path}"
        )

    preflight_result = validate_preflight(output_dir)
    build_manifest("running_full_api_enrichment_staging", args, preflight_result)

    settings = configure_settings(args)
    enricher = ContentEnricher(settings=settings)
    enricher.cache_path = output_dir / "_full_enrichment_cache.json"
    enricher.cache = enricher._load_cache()

    results = enricher.enrich_all(chunks_dir=output_dir)
    runtime_quality = enricher.get_runtime_quality_report()
    quality_report = build_quality_report(
        chunks_dir=output_dir,
        runtime_quality=runtime_quality,
    )
    write_json(quality_report_path, quality_report)

    report = {
        "status": "completed_full_api_enrichment_staging",
        "generated_at": now(),
        "backend": "api",
        "model": args.model,
        "documents": len(results),
        "chunks": sum(len(records) for records in results.values()),
        "new_llm_calls_this_run": enricher._call_count,
        "canonical_artifacts_replaced": False,
        "paid_api_calls": "external_api",
        "manifest_path": str(output_dir / "_enrichment_manifest.json"),
        "quality_report_path": str(quality_report_path),
    }
    write_json(run_report_path, report)
    build_manifest(
        "completed_full_api_enrichment_staging",
        args,
        preflight_result=preflight_result,
        runtime_report=report,
        quality_report=quality_report,
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--disable-qwen-thinking", action="store_true")
    parser.add_argument("--api-extra-body-json", default="")
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = sum((args.estimate, args.preflight, args.prepare, args.run))
    if selected != 1:
        raise SystemExit(
            "Choose exactly one of --estimate, --preflight, --prepare, or --run"
        )

    if args.estimate:
        result = estimate_calls(Path(args.source))
    elif args.preflight:
        result = validate_preflight(Path(args.source))
    elif args.prepare:
        result = prepare_workspace(args)
    else:
        result = run_api(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
