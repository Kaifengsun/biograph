"""Select a BM25-default table gate on all 90 already-observed development queries."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from develop_source_chunk_reranker import dense_rankings, load_corpus, query_hash, read_json, sha256_file
from evaluate_bm25_enrichment_ablation import aggregate, bootstrap_mean_ci, metric_row
from source_chunk_reranker import (
    BM25Index, RerankParameters, SelectiveParameters, rerank_source_chunks,
    selective_rerank_source_chunks,
)


DEFAULT_OUTPUT = Path("outputs/selective_source_chunk_reranker_development_2026-07-15-v1")


def normalized_question(value: str) -> str:
    return " ".join(__import__("re").findall(r"[a-z0-9]+", value.casefold()))


def combined_query_hash(rows: list[dict[str, Any]]) -> str:
    payload = [
        {"annotation_id": row["annotation_id"], "query_slice": row["query_slice"], "query": row["query"], "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"]}
        for row in rows
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def parameter_grid() -> list[SelectiveParameters]:
    return [SelectiveParameters(*values) for values in itertools.product((3, 5, 10), (1, 2, 3), (0.0, 0.25, 0.5, 1.0))]


def selection_key(row: dict[str, Any]) -> tuple[Any, ...]:
    p = row["parameters"]
    return (
        -row["metrics"]["mrr"], -row["metrics"]["hit_at_5"], -row["metrics"]["ndcg_at_5"],
        row["gate_enabled_query_count"], p["table_support_depth"],
        -p["table_support_threshold"], p["table_weight"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-pack", default="data/eval/three_path_evaluation_frozen_2026-07-15.json")
    parser.add_argument("--development-retrieval", default="artifacts/three_path_retrieval/formal_frozen_2026-07-15/per_query.json")
    parser.add_argument("--observed-pack", default="data/eval/bm25_enrichment_heldout_frozen_run_ready_2026-07-15.json")
    parser.add_argument("--observed-retrieval", default="artifacts/three_path_retrieval/bm25_enrichment_heldout_2026-07-15/per_query.json")
    parser.add_argument("--corpus", default="data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
    parser.add_argument("--index", default="artifacts/retrieval_ablation/deepseek-v4-pro-v4/R1_raw/pharma_docs.faiss")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite development output: {output}")
    pack_paths = [Path(args.development_pack), Path(args.observed_pack)]
    retrieval_paths = [Path(args.development_retrieval), Path(args.observed_retrieval)]
    packs = [read_json(path) for path in pack_paths]
    groups = [pack["queries"] for pack in packs]
    if [len(group) for group in groups] != [60, 30]:
        raise ValueError("combined development requires the frozen 60 and observed 30 query sets")
    normalized_groups = [{normalized_question(row["query"]) for row in group} for group in groups]
    if normalized_groups[0] & normalized_groups[1]:
        raise ValueError("the two observed development sets overlap by normalized question")
    queries = groups[0] + groups[1]

    retrieval_by_query: dict[str, dict[str, Any]] = {}
    for path in retrieval_paths:
        for row in read_json(path):
            query = str(row["retrieval"]["query"])
            if query in retrieval_by_query:
                raise ValueError(f"duplicate retrieval query: {query}")
            retrieval_by_query[query] = row["retrieval"]
    missing = [row["annotation_id"] for row in queries if row["query"] not in retrieval_by_query]
    if missing:
        raise ValueError(f"retrieval artifacts are missing queries: {missing}")

    corpus, table_chunk_ids = load_corpus(Path(args.corpus))
    records_by_id = {str(row["chunk_id"]): row for row in corpus}
    bm25 = BM25Index.build(corpus)
    bm25_rankings = [bm25.rank(row["query"], 60) for row in queries]
    dense = dense_rankings([row["query"] for row in queries], Path(args.index), 60)
    global_parameters = RerankParameters()

    baselines = {"BM25": [], "R1_raw": [], "Global_source_RRF": []}
    global_rankings: list[list[str]] = []
    for position, row in enumerate(queries):
        selected_documents = (retrieval_by_query[row["query"]].get("top_down") or {}).get("selected_documents") or []
        global_result = rerank_source_chunks(
            row["query"], bm25_rankings[position], dense[position], records_by_id,
            selected_documents, table_chunk_ids, global_parameters,
        )
        gold = set(row["gold_evidence_chunk_ids"])
        baselines["BM25"].append(metric_row(bm25_rankings[position], gold))
        baselines["R1_raw"].append(metric_row(dense[position], gold))
        baselines["Global_source_RRF"].append(metric_row(global_result["ranking"], gold))
        global_rankings.append(global_result["ranking"])

    grid_results: list[dict[str, Any]] = []
    details_by_grid: dict[str, list[dict[str, Any]]] = {}
    for grid_index, parameters in enumerate(parameter_grid()):
        grid_id = f"grid_{grid_index:03d}"
        details, metric_rows = [], []
        for position, row in enumerate(queries):
            selected_documents = (retrieval_by_query[row["query"]].get("top_down") or {}).get("selected_documents") or []
            result = selective_rerank_source_chunks(
                row["query"], bm25_rankings[position], dense[position], records_by_id,
                selected_documents, table_chunk_ids, parameters,
            )
            metrics = metric_row(result["ranking"], set(row["gold_evidence_chunk_ids"]))
            metric_rows.append(metrics)
            details.append({
                "annotation_id": row["annotation_id"], "dataset_group": "original_60" if position < 60 else "observed_30",
                "query_slice": row["query_slice"], "query": row["query"],
                "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"], "metrics": metrics,
                "selective_reranking": result,
            })
        grid_results.append({
            "grid_id": grid_id, "parameters": asdict(parameters), "metrics": aggregate(metric_rows),
            "gate_enabled_query_count": sum(row["selective_reranking"]["table_gate"]["enabled"] for row in details),
        })
        details_by_grid[grid_id] = details

    selected = min(grid_results, key=selection_key)
    selected_details = details_by_grid[selected["grid_id"]]
    uncertainty = {
        metric: bootstrap_mean_ci(
            [row["metrics"][metric] for row in selected_details], args.bootstrap_iterations,
            args.seed, f"selective90:{metric}",
        )
        for metric in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
    }
    report = {
        "schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dataset_role": "combined_observed_development_only", "new_confirmatory_executed": False,
        "query_count": 90, "group_counts": {"original_60": 60, "observed_30": 30},
        "group_query_hashes": {"original_60": query_hash(groups[0]), "observed_30": query_hash(groups[1])},
        "combined_query_sha256": combined_query_hash(queries),
        "selection_rule": "MRR, Hit@5, nDCG@5, fewer gate activations, lower depth, higher threshold, lower table weight",
        "grid_configuration_count": len(grid_results),
        "baselines": {name: aggregate(rows) for name, rows in baselines.items()},
        "selected": {**selected, "uncertainty": uncertainty},
        "quality_checks": {
            "normalized_question_overlap_zero": not bool(normalized_groups[0] & normalized_groups[1]),
            "all_rankings_source_only": all(set(row["selective_reranking"]["ranking"]) <= set(records_by_id) for row in selected_details),
            "disabled_gate_preserves_bm25": all(
                row["selective_reranking"]["ranking"] == bm25_rankings[position]
                for position, row in enumerate(selected_details)
                if not row["selective_reranking"]["table_gate"]["enabled"]
            ),
            "grid_count_36": len(grid_results) == 36,
        },
        "input_hashes": {
            **{f"pack_{i}": sha256_file(path) for i, path in enumerate(pack_paths, 1)},
            **{f"retrieval_{i}": sha256_file(path) for i, path in enumerate(retrieval_paths, 1)},
            "index": sha256_file(Path(args.index)), "index_metadata": sha256_file(Path(args.index).with_suffix(".meta.json")),
            "selective_code": sha256_file(Path(__file__).with_name("source_chunk_reranker.py")),
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
