"""Tune the deterministic source-chunk reranker on the frozen 60-query development set."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from evaluate_bm25_enrichment_ablation import aggregate, bootstrap_mean_ci, metric_row
from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient
from source_chunk_reranker import BM25Index, RerankParameters, rerank_source_chunks


DEFAULT_EVALUATION = Path("data/eval/three_path_evaluation_frozen_2026-07-15.json")
DEFAULT_RETRIEVAL = Path("artifacts/three_path_retrieval/formal_frozen_2026-07-15/per_query.json")
DEFAULT_CORPUS = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
DEFAULT_INDEX = Path("artifacts/retrieval_ablation/deepseek-v4-pro-v4/R1_raw/pharma_docs.faiss")
DEFAULT_OUTPUT = Path("outputs/source_chunk_reranker_development_2026-07-15-v1")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def query_hash(rows: list[dict[str, Any]]) -> str:
    payload = [
        {
            "annotation_id": row["annotation_id"],
            "query_slice": row["query_slice"],
            "query": row["query"],
            "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
        }
        for row in rows
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_corpus(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    records: list[dict[str, Any]] = []
    table_chunk_ids: set[str] = set()
    for file_path in sorted(path.glob("*_enriched.json")):
        records.extend(read_json(file_path))
    for file_path in sorted(path.glob("*_tables.json")):
        table_chunk_ids.update(
            str(row.get("chunk_id", "")) for row in read_json(file_path) if row.get("chunk_id")
        )
    if len(records) != 2478 or len({row["chunk_id"] for row in records}) != len(records):
        raise ValueError("frozen corpus must contain 2478 unique source chunks")
    return records, table_chunk_ids


def dense_rankings(queries: list[str], index_path: Path, depth: int) -> list[list[str]]:
    metadata = read_json(index_path.with_suffix(".meta.json"))
    if any(row.get("type") != "raw" for row in metadata):
        raise ValueError("R1 baseline must contain raw source records only")
    settings = PipelineSettings()
    settings.embedding = EmbeddingConfig(
        backend="local",
        local_model=settings.embedding.local_model,
        dimension=settings.embedding.dimension,
    )
    embedder = EmbeddingClient(settings.embedding)
    vectors = embedder.embed(queries, batch_size=8)
    faiss.normalize_L2(vectors)
    index = faiss.read_index(str(index_path))
    if index.ntotal != len(metadata):
        raise ValueError("dense index and metadata size mismatch")
    _, indices = index.search(vectors, min(depth, index.ntotal))
    return [
        [str(metadata[index]["chunk_id"]) for index in row if index >= 0]
        for row in indices
    ]


def parameter_grid() -> list[RerankParameters]:
    return [
        RerankParameters(*values)
        for values in itertools.product(
            (1.0, 1.5, 2.0),
            (1.0, 1.5, 2.0),
            (0.0, 0.5, 1.0),
            (0.0, 0.5, 1.0),
            (0.0, 0.5, 1.0),
        )
    ]


def selection_key(row: dict[str, Any]) -> tuple[Any, ...]:
    parameters = row["parameters"]
    values = tuple(parameters[key] for key in (
        "lexical_bm25_weight", "semantic_dense_weight", "explicit_document_weight",
        "table_weight", "hierarchy_weight",
    ))
    nonzero_extras = sum(value != default for value, default in zip(values, (1.0, 1.0, 0.0, 0.0, 0.0), strict=True))
    return (
        -row["metrics"]["mrr"],
        -row["metrics"]["hit_at_5"],
        -row["metrics"]["ndcg_at_5"],
        nonzero_extras,
        sum(values),
        values,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", default=str(DEFAULT_EVALUATION))
    parser.add_argument("--retrieval", default=str(DEFAULT_RETRIEVAL))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite development output: {output}")
    evaluation_path, retrieval_path = Path(args.evaluation), Path(args.retrieval)
    evaluation_pack = read_json(evaluation_path)
    queries = evaluation_pack["queries"]
    if len(queries) != 60:
        raise ValueError("development set must contain exactly 60 queries")
    retrieval_records = read_json(retrieval_path)
    retrieval_rows = {str(row["retrieval"]["query"]): row["retrieval"] for row in retrieval_records}
    if len(retrieval_rows) != len(retrieval_records):
        raise ValueError("duplicate query text in development retrieval artifact")
    missing_queries = [row["annotation_id"] for row in queries if row["query"] not in retrieval_rows]
    if missing_queries:
        raise ValueError(f"development retrieval is missing queries: {missing_queries}")

    corpus, table_chunk_ids = load_corpus(Path(args.corpus))
    records_by_id = {str(row["chunk_id"]): row for row in corpus}
    bm25 = BM25Index.build(corpus)
    bm25_rankings = [bm25.rank(row["query"], 60) for row in queries]
    dense = dense_rankings([row["query"] for row in queries], Path(args.index), 60)

    baseline_metrics = {"BM25": [], "R1_raw": [], "Global_source_RRF": []}
    global_parameters = RerankParameters()
    global_details: list[dict[str, Any]] = []
    for position, row in enumerate(queries):
        gold = set(row["gold_evidence_chunk_ids"])
        selected_documents = (retrieval_rows[row["query"]].get("top_down") or {}).get("selected_documents") or []
        global_result = rerank_source_chunks(
            row["query"], bm25_rankings[position], dense[position], records_by_id,
            selected_documents, table_chunk_ids, global_parameters,
        )
        baseline_metrics["BM25"].append(metric_row(bm25_rankings[position], gold))
        baseline_metrics["R1_raw"].append(metric_row(dense[position], gold))
        baseline_metrics["Global_source_RRF"].append(metric_row(global_result["ranking"], gold))
        global_details.append(global_result)

    grid_results: list[dict[str, Any]] = []
    details_by_grid: dict[str, list[dict[str, Any]]] = {}
    for index, parameters in enumerate(parameter_grid()):
        grid_id = f"grid_{index:03d}"
        details: list[dict[str, Any]] = []
        metric_rows: list[dict[str, float]] = []
        for position, row in enumerate(queries):
            retrieval = retrieval_rows[row["query"]]
            selected_documents = (retrieval.get("top_down") or {}).get("selected_documents") or []
            result = rerank_source_chunks(
                row["query"], bm25_rankings[position], dense[position], records_by_id,
                selected_documents, table_chunk_ids, parameters,
            )
            metrics = metric_row(result["ranking"], set(row["gold_evidence_chunk_ids"]))
            metric_rows.append(metrics)
            details.append({
                "annotation_id": row["annotation_id"], "query_slice": row["query_slice"],
                "query": row["query"], "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
                "metrics": metrics, "reranking": result,
            })
        grid_results.append({"grid_id": grid_id, "parameters": asdict(parameters), "metrics": aggregate(metric_rows)})
        details_by_grid[grid_id] = details

    selected = min(grid_results, key=selection_key)
    selected_details = details_by_grid[selected["grid_id"]]
    uncertainty = {
        metric: bootstrap_mean_ci(
            [row["metrics"][metric] for row in selected_details],
            args.bootstrap_iterations, args.seed, f"selected:{metric}",
        )
        for metric in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
    }
    route_counts: dict[str, int] = {}
    graph_enabled_count = 0
    for row in selected_details:
        route = row["reranking"]["route"]
        route_counts[route["text_route"]] = route_counts.get(route["text_route"], 0) + 1
        graph_enabled_count += int(route["graph_enabled"])

    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dataset_role": "development_only",
        "heldout_executed": False,
        "query_count": len(queries),
        "query_content_sha256": query_hash(queries),
        "candidate_depth_per_channel": 30,
        "baseline_output_depth": 60,
        "selection_rule": "MRR, Hit@5, nDCG@5, sparsity, magnitude, parameter tuple",
        "grid_configuration_count": len(grid_results),
        "baselines": {name: aggregate(rows) for name, rows in baseline_metrics.items()},
        "selected": {**selected, "uncertainty": uncertainty},
        "route_counts": route_counts,
        "graph_enabled_query_count": graph_enabled_count,
        "quality_checks": {
            "all_rankings_source_only": all(
                set(row["reranking"]["ranking"]) <= set(records_by_id) for row in selected_details
            ),
            "unique_selected_rankings": all(
                len(row["reranking"]["ranking"]) == len(set(row["reranking"]["ranking"]))
                for row in selected_details
            ),
            "grid_count_243": len(grid_results) == 243,
        },
        "input_hashes": {
            "evaluation": sha256_file(evaluation_path),
            "retrieval": sha256_file(retrieval_path),
            "index": sha256_file(Path(args.index)),
            "index_metadata": sha256_file(Path(args.index).with_suffix(".meta.json")),
            "reranker_code": sha256_file(Path(__file__).with_name("source_chunk_reranker.py")),
            "development_code": sha256_file(Path(__file__)),
        },
    }
    if not all(report["quality_checks"].values()):
        raise AssertionError(report["quality_checks"])
    output.mkdir(parents=True)
    (output / "development_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "grid_results.json").write_text(json.dumps(grid_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "selected_per_query.json").write_text(json.dumps(selected_details, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "selected": selected, "baselines": report["baselines"]}, indent=2))


if __name__ == "__main__":
    main()
