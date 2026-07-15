"""Build a non-destructive canonical chunk staging directory.

This script intentionally writes only to a new staging directory. It refuses to
overwrite JSON files so the existing canonical artifacts remain untouched until
the staged output has been reviewed and replacement is explicitly approved.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from pharma_doc_pipeline.config import MD_DIR, PipelineSettings
from pharma_doc_pipeline.step_02_chunk import HierarchicalChunker, save_chunks


DEFAULT_OUTPUT_DIR = Path("data/staging/chunks_2026-06-v2")

CANONICAL_DOC_ID_MAP = {
    "ema_gmp_annex11": "ema_gmp_annex_11",
    "ich_q1_draft2025": "ich_q1_draft_2025",
}

EXCLUDED_MARKDOWN_STEMS = {
    "arxiv_supply_chain": (
        "Mislabelled source: arXiv:2305.09617 is a medical question-answering "
        "paper, not a pharmaceutical supply-chain source."
    ),
}


def canonical_doc_id(md_path: Path) -> str:
    return CANONICAL_DOC_ID_MAP.get(md_path.stem, md_path.stem)


def assert_empty_output_dir(output_dir: Path) -> None:
    existing_json = sorted(output_dir.glob("*.json"))
    if existing_json:
        names = ", ".join(path.name for path in existing_json[:5])
        raise RuntimeError(
            f"Refusing to overwrite staging JSON in {output_dir}: {names}"
        )


def build_staging(output_dir: Path) -> dict:
    assert_empty_output_dir(output_dir)

    settings = PipelineSettings()
    chunker = HierarchicalChunker(config=settings.chunking)
    markdown_files = sorted(MD_DIR.rglob("*.md"))

    all_chunks = {}
    source_paths = {}
    for md_path in markdown_files:
        if md_path.stem in EXCLUDED_MARKDOWN_STEMS:
            print(f"[exclude] {md_path.stem}: {EXCLUDED_MARKDOWN_STEMS[md_path.stem]}")
            continue
        doc_id = canonical_doc_id(md_path)
        if doc_id in all_chunks:
            raise RuntimeError(f"Duplicate canonical doc_id: {doc_id}")

        print(f"[chunk] {md_path.stem} -> {doc_id}", flush=True)
        chunks = chunker.chunk_document(md_path, doc_id=doc_id)
        all_chunks[doc_id] = chunks
        source_paths[doc_id] = str(md_path)

    save_chunks(all_chunks, output_dir=output_dir)

    manifest = {
        "generated_at": date.today().isoformat(),
        "status": "staged_raw_chunks_only",
        "output_dir": str(output_dir),
        "documents": len(all_chunks),
        "chunks": sum(len(chunks) for chunks in all_chunks.values()),
        "max_chars": max(
            (chunk.char_count for chunks in all_chunks.values() for chunk in chunks),
            default=0,
        ),
        "canonical_doc_id_map": CANONICAL_DOC_ID_MAP,
        "excluded_markdown_stems": EXCLUDED_MARKDOWN_STEMS,
        "source_paths": source_paths,
        "per_document": {
            doc_id: {
                "chunks": len(chunks),
                "max_chars": max((chunk.char_count for chunk in chunks), default=0),
                "empty_chunks": sum(not chunk.content.strip() for chunk in chunks),
            }
            for doc_id, chunks in all_chunks.items()
        },
        "next_gate": (
            "Review staged chunks before enriching, replacing canonical JSON, "
            "rebuilding FAISS, or modifying Neo4j."
        ),
    }
    manifest_path = output_dir / "_staging_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[done] staged manifest: {manifest_path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="New staging directory. Existing JSON files are never overwritten.",
    )
    args = parser.parse_args()
    build_staging(args.output)


if __name__ == "__main__":
    main()
