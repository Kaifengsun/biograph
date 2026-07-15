"""Prepare and optionally run a small local-Ollama enrichment pilot."""

import argparse
import json
from pathlib import Path

from pharma_doc_pipeline.config import PipelineSettings
from pharma_doc_pipeline.step_03_enrich import ContentEnricher


SOURCE_DIR = Path("data/staging/chunks_2026-06-v2")
PILOT_DIR = Path("data/staging/enrichment_pilot_2026-06-v3")
PILOT_DOCS = ("ich_q7", "ich_q6b", "fda_cgmp_guidance")


def select_representative_chunks(records: list[dict]) -> list[dict]:
    eligible = sorted(
        (record for record in records if len(record.get("content", "")) >= 100),
        key=lambda record: record.get("char_count", len(record.get("content", ""))),
    )
    if not eligible:
        return []
    positions = (0, len(eligible) // 2, len(eligible) - 1)
    selected = []
    seen = set()
    for position in positions:
        record = eligible[position]
        chunk_id = record.get("chunk_id")
        if chunk_id and chunk_id not in seen:
            selected.append(record)
            seen.add(chunk_id)
    return selected


def prepare_pilot() -> dict:
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    if list(PILOT_DIR.glob("*.json")):
        raise RuntimeError(f"Refusing to overwrite existing pilot JSON in {PILOT_DIR}")

    selected_by_doc = {}
    for doc_id in PILOT_DOCS:
        source_path = SOURCE_DIR / f"{doc_id}_chunks.json"
        records = json.loads(source_path.read_text(encoding="utf-8"))
        selected = select_representative_chunks(records)
        selected_by_doc[doc_id] = selected
        output_path = PILOT_DIR / f"{doc_id}_chunks.json"
        output_path.write_text(
            json.dumps(selected, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    manifest = {
        "status": "prepared_local_ollama_pilot",
        "model": "qwen2.5:14b",
        "source_dir": str(SOURCE_DIR),
        "pilot_dir": str(PILOT_DIR),
        "documents": list(PILOT_DOCS),
        "selected_chunks": {
            doc_id: [
                {
                    "chunk_id": record["chunk_id"],
                    "char_count": record.get(
                        "char_count",
                        len(record.get("content", "")),
                    ),
                }
                for record in selected
            ]
            for doc_id, selected in selected_by_doc.items()
        },
        "canonical_artifacts_replaced": False,
        "paid_api_calls": 0,
    }
    (PILOT_DIR / "_pilot_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def run_local_pilot() -> dict:
    if not (PILOT_DIR / "_pilot_manifest.json").exists():
        raise RuntimeError("Prepare the pilot before running enrichment")
    if list(PILOT_DIR.glob("*_enriched.json")):
        raise RuntimeError(f"Refusing to overwrite pilot enrichment in {PILOT_DIR}")

    settings = PipelineSettings()
    settings.llm.backend = "ollama"
    settings.llm.ollama_model = "qwen2.5:14b"

    enricher = ContentEnricher(settings=settings)
    enricher.cache_path = PILOT_DIR / "_pilot_enrichment_cache.json"
    enricher.cache = {}
    results = enricher.enrich_all(chunks_dir=PILOT_DIR)

    report = {
        "status": "completed_local_ollama_pilot",
        "model": settings.llm.ollama_model,
        "documents": len(results),
        "chunks": sum(len(records) for records in results.values()),
        "local_llm_calls": enricher._call_count,
        "paid_api_calls": 0,
        "canonical_artifacts_replaced": False,
    }
    (PILOT_DIR / "_pilot_run_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run-local", action="store_true")
    args = parser.parse_args()

    if args.prepare == args.run_local:
        raise SystemExit("Choose exactly one of --prepare or --run-local")

    result = prepare_pilot() if args.prepare else run_local_pilot()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
