"""Refine legacy-to-frozen evidence candidates with the R2 semantic index.

The output remains a candidate annotation artifact. Semantic similarity narrows
review effort but does not turn the result into formal ground truth.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import faiss
import numpy as np

from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient


DEFAULT_CANDIDATES = Path("data/eval/eval_queries_deepseek_v4_candidate_2026-07-10.json")
DEFAULT_LEGACY = Path("data/chunks")
DEFAULT_INDEX = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4/R2_summary")
DEFAULT_OUTPUT = Path("data/eval/eval_queries_deepseek_v4_semantic_candidate_2026-07-10.json")
DEFAULT_REPORT = Path("data/eval/deepseek_v4_semantic_alignment_report_2026-07-10.json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def old_text(record: Dict[str, Any]) -> str:
    return "\n".join(
        str(part).strip()
        for part in (record.get("parents_context", ""), record.get("heading", ""), record.get("content", ""))
        if str(part).strip()
    )[:2000]


def load_legacy(directory: Path) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*_enriched.json")):
        for row in read_json(path):
            chunk_id = row.get("chunk_id", "")
            if chunk_id:
                records[normalize_id(chunk_id)] = row
    if not records:
        raise RuntimeError(f"no legacy enriched records found in {directory}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine candidate evidence with semantic search")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--legacy", default=str(DEFAULT_LEGACY))
    parser.add_argument("--index-dir", default=str(DEFAULT_INDEX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--top-k", type=int, default=12)
    args = parser.parse_args()

    output, report_path = Path(args.output), Path(args.report)
    if output.exists() or report_path.exists():
        raise RuntimeError("refusing to overwrite existing semantic candidate artifacts")

    queries = read_json(Path(args.candidates))
    legacy = load_legacy(Path(args.legacy))
    index_dir = Path(args.index_dir)
    index = faiss.read_index(str(index_dir / "pharma_docs.faiss"))
    metadata = read_json(index_dir / "pharma_docs.meta.json")

    settings = PipelineSettings()
    settings.embedding = EmbeddingConfig(
        backend="local",
        local_model=settings.embedding.local_model,
        dimension=settings.embedding.dimension,
    )
    embedder = EmbeddingClient(settings.embedding)

    mappings = []
    cosine_scores: List[float] = []
    for query in queries:
        semantic_mappings = []
        for mapping in query.get("candidate_evidence_mappings", []):
            old = legacy.get(normalize_id(mapping["legacy_chunk_id"]))
            if old is None:
                continue
            embedding = embedder.embed([old_text(old)], batch_size=1).astype(np.float32)
            faiss.normalize_L2(embedding)
            search_k = min(index.ntotal, max(args.top_k * 20, 200))
            scores, positions = index.search(embedding, search_k)
            candidates = []
            old_doc_id = old.get("doc_id", "")
            for score, position in zip(scores[0], positions[0]):
                if position < 0 or position >= len(metadata):
                    continue
                meta = metadata[position]
                if meta.get("doc_id") != old_doc_id:
                    continue
                candidates.append(
                    {
                        "new_chunk_id": meta.get("chunk_id", ""),
                        "new_heading": meta.get("heading", ""),
                        "semantic_score": round(float(score), 4),
                    }
                )
                if len(candidates) >= args.top_k:
                    break
            if not candidates:
                continue
            best = candidates[0]
            semantic_mapping = {
                **mapping,
                "candidate_new_chunk_id": best["new_chunk_id"],
                "candidate_new_heading": best["new_heading"],
                "semantic_score": best["semantic_score"],
                "semantic_alternatives": candidates[1:],
                "needs_human_review": True,
            }
            semantic_mappings.append(semantic_mapping)
            mappings.append(semantic_mapping)
            cosine_scores.append(best["semantic_score"])

        query["semantic_candidate_evidence_mappings"] = semantic_mappings
        query["semantic_candidate_relevant_chunk_ids"] = list(dict.fromkeys(
            item["candidate_new_chunk_id"] for item in semantic_mappings
        ))
        query["status"] = "semantic_candidate_mapped_needs_review"
        query["eligible_for_formal_evaluation"] = False

    report = {
        "candidate_input": str(args.candidates),
        "legacy_corpus": str(args.legacy),
        "semantic_index": str(index_dir),
        "queries": len(queries),
        "labels_refined": len(mappings),
        "semantic_score_summary": {
            "min": round(min(cosine_scores), 4) if cosine_scores else None,
            "mean": round(sum(cosine_scores) / len(cosine_scores), 4) if cosine_scores else None,
            "below_0_5": sum(score < 0.5 for score in cosine_scores),
            "below_0_7": sum(score < 0.7 for score in cosine_scores),
        },
        "formal_evaluation_ready": False,
        "review_requirement": (
            "Confirm semantic candidate evidence against the query and frozen corpus before "
            "setting eligible_for_formal_evaluation to true."
        ),
    }
    write_json(output, queries)
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
