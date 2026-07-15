"""Build non-destructive R1-R4 FAISS retrieval ablation indexes.

All indexes are built from one frozen enriched corpus and one embedding model.
They differ only in the evidence-side text exposed to retrieval:

R1: raw chunk text
R2: raw chunk text plus generated summary
R3: R2 plus HyDE-question sidecar vectors
R4: R3 plus table-summary sidecar vectors
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient, FAISSIndex


DEFAULT_SOURCE = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
DEFAULT_OUTPUT = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4")
MAX_TEXT_CHARS = 2000


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def join_text(*parts: str) -> str:
    return "\n".join(str(part).strip() for part in parts if str(part).strip())


def raw_chunk_text(record: Dict[str, Any]) -> str:
    return join_text(
        record.get("parents_context", ""),
        record.get("heading", ""),
        record.get("content", ""),
    )


def summary_chunk_text(record: Dict[str, Any]) -> str:
    summary = record.get("summary", "")
    if not summary:
        return raw_chunk_text(record)
    return join_text(
        record.get("parents_context", ""),
        record.get("heading", ""),
        summary,
        record.get("content", ""),
    )


def base_metadata(record: Dict[str, Any], record_type: str) -> Dict[str, Any]:
    return {
        "chunk_id": record.get("chunk_id", ""),
        "doc_id": record.get("doc_id", ""),
        "heading": record.get("heading", ""),
        "parents_context": record.get("parents_context", ""),
        "level": record.get("level", 0),
        "type": record_type,
    }


def load_records(source: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    chunk_records: List[Dict[str, Any]] = []
    table_records: List[Dict[str, Any]] = []

    for path in sorted(source.glob("*_enriched.json")):
        records = read_json(path)
        if not isinstance(records, list):
            raise ValueError(f"expected a list: {path}")
        chunk_records.extend(records)

    known_chunks = {record.get("chunk_id", "") for record in chunk_records}
    heading_by_chunk = {
        record.get("chunk_id", ""): record.get("heading", "")
        for record in chunk_records
    }
    for path in sorted(source.glob("*_tables.json")):
        for table in read_json(path):
            summary = str(table.get("table_summary", "")).strip()
            chunk_id = str(table.get("chunk_id", "")).strip()
            if not summary or chunk_id not in known_chunks:
                continue
            table_records.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": chunk_id.split("_C", 1)[0],
                    "heading": heading_by_chunk.get(chunk_id, ""),
                    "table_summary": summary,
                    "source_file": path.name,
                }
            )

    if not chunk_records:
        raise RuntimeError(f"no enriched records found in {source}")
    return chunk_records, table_records


def build_index(
    variant_dir: Path,
    client: EmbeddingClient,
    batches: List[Tuple[str, List[Dict[str, Any]], np.ndarray]],
) -> Dict[str, Any]:
    variant_dir.mkdir(parents=True)
    index = FAISSIndex(
        dimension=client.dimension,
        index_path=variant_dir / "pharma_docs.faiss",
    )
    counts: Dict[str, int] = {}
    for label, metadata, embeddings in batches:
        if len(metadata) != len(embeddings):
            raise ValueError(f"metadata/embedding mismatch for {label}")
        index.add(np.array(embeddings, dtype=np.float32, copy=True), metadata)
        counts[label] = len(metadata)
    index.save()
    manifest = {
        "variant_dir": str(variant_dir),
        "vector_count": index.index.ntotal,
        "components": counts,
        "index_file": "pharma_docs.faiss",
        "metadata_file": "pharma_docs.meta.json",
    }
    write_json(variant_dir / "variant_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R1-R4 staging FAISS indexes")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output}")
    if not source.exists():
        raise FileNotFoundError(source)

    chunks, tables = load_records(source)
    raw_texts = [raw_chunk_text(record)[:MAX_TEXT_CHARS] for record in chunks]
    summary_texts = [summary_chunk_text(record)[:MAX_TEXT_CHARS] for record in chunks]
    raw_metas = [base_metadata(record, "raw") for record in chunks]
    summary_metas = [base_metadata(record, "summary") for record in chunks]

    hyde_texts: List[str] = []
    hyde_metas: List[Dict[str, Any]] = []
    for record in chunks:
        for question in record.get("hyde_questions", []) or []:
            text = str(question).strip()
            if not text:
                continue
            meta = base_metadata(record, "hyde")
            meta["hyde_question"] = text
            hyde_texts.append(text)
            hyde_metas.append(meta)

    table_texts = [
        join_text(record["heading"], record["table_summary"])[:MAX_TEXT_CHARS]
        for record in tables
    ]
    table_metas = [
        {
            "chunk_id": record["chunk_id"],
            "doc_id": record["doc_id"],
            "heading": record["heading"],
            "parents_context": "",
            "level": 0,
            "type": "table_summary",
            "source_file": record["source_file"],
        }
        for record in tables
    ]

    settings = PipelineSettings()
    settings.embedding = EmbeddingConfig(
        backend="local",
        local_model=settings.embedding.local_model,
        dimension=settings.embedding.dimension,
    )
    client = EmbeddingClient(settings.embedding)
    print(f"Embedding raw chunk text: {len(raw_texts)}")
    raw_embeddings = client.embed(raw_texts, batch_size=args.batch_size)
    print(f"Embedding summary-enriched chunk text: {len(summary_texts)}")
    summary_embeddings = client.embed(summary_texts, batch_size=args.batch_size)
    print(f"Embedding HyDE sidecars: {len(hyde_texts)}")
    hyde_embeddings = client.embed(hyde_texts, batch_size=args.batch_size)
    print(f"Embedding table-summary sidecars: {len(table_texts)}")
    table_embeddings = client.embed(table_texts, batch_size=args.batch_size)

    output.mkdir(parents=True)
    variants = {
        "R1_raw": build_index(
            output / "R1_raw", client, [("raw", raw_metas, raw_embeddings)]
        ),
        "R2_summary": build_index(
            output / "R2_summary", client, [("summary", summary_metas, summary_embeddings)]
        ),
        "R3_hyde": build_index(
            output / "R3_hyde", client,
            [("summary", summary_metas, summary_embeddings), ("hyde", hyde_metas, hyde_embeddings)],
        ),
        "R4_table": build_index(
            output / "R4_table", client,
            [
                ("summary", summary_metas, summary_embeddings),
                ("hyde", hyde_metas, hyde_embeddings),
                ("table_summary", table_metas, table_embeddings),
            ],
        ),
    }
    manifest = {
        "source": str(source),
        "embedding_model": settings.embedding.local_model,
        "chunk_count": len(chunks),
        "hyde_sidecar_count": len(hyde_texts),
        "table_sidecar_count": len(table_texts),
        "variants": variants,
        "canonical_artifacts_replaced": False,
    }
    write_json(output / "ablation_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
