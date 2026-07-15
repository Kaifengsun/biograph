"""Evaluate locked source-only retrieval methods on an exploratory or confirmatory pack."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from develop_source_chunk_reranker import dense_rankings, load_corpus, query_hash, read_json, sha256_file
from evaluate_bm25_enrichment_ablation import (
    adjust_holm, aggregate, bootstrap_mean_ci, metric_row, paired_comparison,
)
from source_chunk_reranker import (
    BM25Index, RerankParameters, SelectiveParameters, rerank_source_chunks,
    selective_rerank_source_chunks,
)


BASE_METHODS = ("BM25_context_matched", "R1_raw", "Global_source_RRF")


def validate_role(pack: dict[str, Any], role: str) -> None:
    if role == "formal_confirmatory":
        if not pack.get("confirmatory_for_source_chunk_reranker"):
            raise ValueError("formal execution requires a dedicated confirmatory pack")
        if not pack.get("formal_metrics_ready") or pack.get("retrieval_execution_prohibited"):
            raise ValueError("confirmatory pack is not activated for formal execution")


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Source-Chunk Reranker Evaluation", "",
        f"Role: `{report['evaluation_role']}`", "",
        "| Method | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in report["methods"]:
        row = report["aggregate"][method]
        lines.append(
            f"| {method} | {row['hit_at_1']:.3f} | {row['hit_at_3']:.3f} | "
            f"{row['hit_at_5']:.3f} | {row['mrr']:.3f} | {row['ndcg_at_5']:.3f} |"
        )
    lines.extend(["", "## Paired comparisons", ""])
    for family, comparisons in report["paired_comparisons"].items():
        lines.append(f"### {family}")
        for metric, row in comparisons.items():
            lines.append(
                f"- {metric}: delta {row['delta_mean']:.4f}, 95% CI "
                f"[{row['delta_ci_95_low']:.4f}, {row['delta_ci_95_high']:.4f}], "
                f"Holm p={row['p_value_holm']:.4g}."
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--retrieval", required=True)
    parser.add_argument("--method-lock", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evaluation-role", choices=("exploratory_observed", "formal_confirmatory"), required=True)
    parser.add_argument("--corpus", default="data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
    parser.add_argument("--index", default="artifacts/retrieval_ablation/deepseek-v4-pro-v4/R1_raw/pharma_docs.faiss")
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    output = Path(args.output)
    siblings = [output, output.with_name(output.stem + "-per-query.json"), output.with_name(output.stem + "-per-query.csv"), output.with_suffix(".md")]
    if any(path.exists() for path in siblings):
        raise RuntimeError(f"refusing to overwrite evaluation output: {output}")

    pack_path, retrieval_path, lock_path = Path(args.pack), Path(args.retrieval), Path(args.method_lock)
    pack = read_json(pack_path)
    validate_role(pack, args.evaluation_role)
    queries = pack.get("queries", [])
    if not queries:
        raise ValueError("evaluation pack has no queries")
    lock = read_json(lock_path)
    if not str(lock.get("lock_status", "")).startswith("locked_before_confirmatory"):
        raise ValueError("method lock has unexpected status")
    method_family = lock.get("method_family", "routed")
    if method_family == "selective_table_gate":
        selective_parameters = SelectiveParameters(**lock["selected_parameters"])
        routed_parameters = None
        treatment_name = "Selective_table_gate"
    else:
        selective_parameters = None
        routed_parameters = RerankParameters(**lock["selected_parameters"])
        treatment_name = "Query_routed_source_reranker"
    methods = (*BASE_METHODS, treatment_name)

    retrieval_records = read_json(retrieval_path)
    retrieval_by_query = {str(row["retrieval"]["query"]): row["retrieval"] for row in retrieval_records}
    if len(retrieval_by_query) != len(retrieval_records):
        raise ValueError("duplicate retrieval query text")
    missing = [row["annotation_id"] for row in queries if row["query"] not in retrieval_by_query]
    if missing:
        raise ValueError(f"retrieval artifact is missing queries: {missing}")

    corpus, table_chunk_ids = load_corpus(Path(args.corpus))
    records_by_id = {str(row["chunk_id"]): row for row in corpus}
    bm25 = BM25Index.build(corpus)
    bm25_rankings = [bm25.rank(row["query"], 60) for row in queries]
    dense = dense_rankings([row["query"] for row in queries], Path(args.index), 60)
    global_parameters = RerankParameters()

    per_query: list[dict[str, Any]] = []
    for position, row in enumerate(queries):
        retrieval = retrieval_by_query[row["query"]]
        selected_documents = (retrieval.get("top_down") or {}).get("selected_documents") or []
        global_result = rerank_source_chunks(
            row["query"], bm25_rankings[position], dense[position], records_by_id,
            selected_documents, table_chunk_ids, global_parameters,
        )
        if selective_parameters is not None:
            routed_result = selective_rerank_source_chunks(
                row["query"], bm25_rankings[position], dense[position], records_by_id,
                selected_documents, table_chunk_ids, selective_parameters,
            )
        else:
            routed_result = rerank_source_chunks(
                row["query"], bm25_rankings[position], dense[position], records_by_id,
                selected_documents, table_chunk_ids, routed_parameters,
            )
        rankings = {
            "BM25_context_matched": bm25_rankings[position],
            "R1_raw": dense[position],
            "Global_source_RRF": global_result["ranking"],
            treatment_name: routed_result["ranking"],
        }
        gold = set(row["gold_evidence_chunk_ids"])
        per_query.append({
            "annotation_id": row["annotation_id"], "query_slice": row["query_slice"],
            "query": row["query"], "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
            "metrics": {method: metric_row(rankings[method], gold) for method in methods},
            "rankings": rankings, "reranking_audit": routed_result,
            "graph_evidence_available": bool((retrieval.get("graph_path") or {}).get("structured_evidence") or (retrieval.get("graph_path") or {}).get("paths")),
        })

    aggregate_metrics = {method: aggregate([row["metrics"][method] for row in per_query]) for method in methods}
    by_slice = {
        query_slice: {
            method: aggregate([row["metrics"][method] for row in per_query if row["query_slice"] == query_slice])
            for method in methods
        }
        for query_slice in sorted({row["query_slice"] for row in per_query})
    }
    uncertainty = {
        method: {
            metric: bootstrap_mean_ci(
                [row["metrics"][method][metric] for row in per_query],
                args.bootstrap_iterations, args.seed, f"{args.evaluation_role}:{method}:{metric}",
            )
            for metric in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
        }
        for method in methods
    }
    paired: dict[str, dict[str, Any]] = {}
    for family, treatment in (
        (f"{treatment_name}_vs_BM25", treatment_name),
        ("Global_vs_BM25", "Global_source_RRF"),
    ):
        comparisons = {
            metric: paired_comparison(
                [row["metrics"][treatment][metric] for row in per_query],
                [row["metrics"]["BM25_context_matched"][metric] for row in per_query],
                metric, args.bootstrap_iterations, args.seed, f"{args.evaluation_role}:{family}:{metric}",
            )
            for metric in ("hit_at_5", "mrr", "ndcg_at_5")
        }
        adjust_holm(comparisons)
        paired[family] = comparisons

    report = {
        "schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "evaluation_role": args.evaluation_role, "formal_metrics": args.evaluation_role == "formal_confirmatory",
        "query_count": len(queries), "query_content_sha256": query_hash(queries),
        "methods": list(methods), "method_family": method_family, "selected_parameters": lock["selected_parameters"],
        "aggregate": aggregate_metrics, "uncertainty": uncertainty, "by_slice": by_slice,
        "paired_comparisons": paired,
        "quality_checks": {
            "all_routed_rankings_source_only": all(set(row["rankings"][treatment_name]) <= set(records_by_id) for row in per_query),
            "all_rankings_unique": all(len(ranking) == len(set(ranking)) for row in per_query for ranking in row["rankings"].values()),
            "graph_excluded_from_text_metrics": True,
        },
        "input_hashes": {
            "pack": sha256_file(pack_path), "retrieval": sha256_file(retrieval_path),
            "method_lock": sha256_file(lock_path), "evaluation_code": sha256_file(Path(__file__)),
        },
    }
    if not all(report["quality_checks"].values()):
        raise AssertionError(report["quality_checks"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    siblings[1].write_text(json.dumps(per_query, ensure_ascii=False, indent=2), encoding="utf-8")
    output.with_suffix(".md").write_text(markdown_report(report), encoding="utf-8")
    with siblings[2].open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["annotation_id", "query_slice", "method", "hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5"])
        for row in per_query:
            for method in methods:
                metric = row["metrics"][method]
                writer.writerow([row["annotation_id"], row["query_slice"], method, *[metric[key] for key in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")]])
    print(json.dumps({"output": str(output), "role": args.evaluation_role, "aggregate": aggregate_metrics}, indent=2))


if __name__ == "__main__":
    main()
