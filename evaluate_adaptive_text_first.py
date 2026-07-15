"""Evaluate locked text-first baselines and adaptive variants on a run-ready frozen set."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adaptive_text_first import AdaptiveParameters, adaptive_rank
from analyze_three_path_ablation import mean_ci, paired_test, rrf_rank
from statsmodels.stats.multitest import multipletests
from three_path_evaluation import hit_at_k, ndcg_at_k, reciprocal_rank, sha256_file, validate_frozen_pack


VARIANTS = (
    "bottom_up",
    "top_down",
    "graph_path",
    "text_rrf",
    "unconditional_three_path_rrf",
    "adaptive_without_graph",
    "adaptive_full",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_ids(retrieval: dict[str, Any], route: str) -> list[str]:
    value = retrieval.get(route) or []
    if isinstance(value, dict):
        value = value.get("evidence") or []
    return list(dict.fromkeys(str(row["chunk_id"]) for row in value if row.get("chunk_id")))


def metric_row(ranking: list[str], gold: set[str]) -> dict[str, float]:
    return {
        "hit_at_1": hit_at_k(ranking, gold, 1),
        "hit_at_3": hit_at_k(ranking, gold, 3),
        "hit_at_5": hit_at_k(ranking, gold, 5),
        "mrr": reciprocal_rank(ranking, gold),
        "ndcg_at_5": ndcg_at_k(ranking, gold, 5),
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    return {
        name: round(sum(row[name] for row in rows) / len(rows), 6)
        for name in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
    }


def adjust_holm(comparisons: dict[str, dict[str, Any]]) -> None:
    rejected, adjusted, _sidak, _bonf = multipletests(
        [row["p_value_raw"] for row in comparisons.values()], alpha=0.05, method="holm"
    )
    for row, adjusted_p, rejected_flag in zip(comparisons.values(), adjusted, rejected, strict=True):
        row["p_value_holm"] = round(float(adjusted_p), 8)
        row["significant_after_holm_0_05"] = bool(rejected_flag)


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Locked Adaptive Text-First Held-Out Evaluation",
        "",
        f"Queries: {report['query_count']}",
        "",
        "| Variant | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "bottom_up": "Bottom-up",
        "top_down": "Top-down",
        "graph_path": "Graph path",
        "text_rrf": "Bottom-up + Top-down RRF",
        "unconditional_three_path_rrf": "Unconditional three-path RRF",
        "adaptive_without_graph": "Adaptive without graph",
        "adaptive_full": "Full adaptive text-first",
    }
    for variant in VARIANTS:
        values = report["aggregate"][variant]
        lines.append(
            f"| {labels[variant]} | {values['hit_at_1']:.3f} | {values['hit_at_3']:.3f} | "
            f"{values['hit_at_5']:.3f} | {values['mrr']:.3f} | {values['ndcg_at_5']:.3f} |"
        )
    lines.extend(["", "## Predeclared paired comparisons", ""])
    for family, comparisons in report["paired_comparisons"].items():
        lines.append(f"### {family.replace('_', ' ').title()}")
        for metric, row in comparisons.items():
            lines.append(
                f"- {metric}: delta {row['delta_mean']:.4f}, 95% CI [{row['delta_ci_95_low']:.4f}, "
                f"{row['delta_ci_95_high']:.4f}], Holm p={row['p_value_holm']:.4g}."
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--retrieval", required=True)
    parser.add_argument("--development-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    pack_path = Path(args.pack)
    retrieval_path = Path(args.retrieval)
    development_report_path = Path(args.development_report)
    output_path = Path(args.output)
    markdown_path = output_path.with_suffix(".md")
    per_query_path = output_path.with_name(output_path.stem + "-per-query.json")
    if any(path.exists() for path in (output_path, markdown_path, per_query_path)):
        raise RuntimeError(f"refusing to overwrite held-out evaluation output: {output_path}")

    evaluation_rows = validate_frozen_pack(read_json(pack_path))
    retrieval_records = read_json(retrieval_path)
    retrieval_by_query = {str(row["retrieval"]["query"]): row["retrieval"] for row in retrieval_records}
    if len(retrieval_by_query) != len(retrieval_records):
        raise ValueError("duplicate held-out retrieval queries")
    missing = [row["annotation_id"] for row in evaluation_rows if row["query"] not in retrieval_by_query]
    if missing:
        raise ValueError(f"held-out retrieval is missing queries: {missing}")

    selected_parameters = AdaptiveParameters(**read_json(development_report_path)["selected"]["parameters"])
    no_graph_parameters = replace(selected_parameters, graph_weight=0.0)
    per_query = []
    for row in evaluation_rows:
        retrieval = retrieval_by_query[row["query"]]
        components = {route: evidence_ids(retrieval, route) for route in ("bottom_up", "top_down", "graph_path")}
        rankings = {
            **components,
            "text_rrf": rrf_rank([components["bottom_up"], components["top_down"]]),
            "unconditional_three_path_rrf": rrf_rank([components["bottom_up"], components["top_down"], components["graph_path"]]),
            "adaptive_without_graph": adaptive_rank(retrieval, no_graph_parameters)["ranking"],
            "adaptive_full": adaptive_rank(retrieval, selected_parameters)["ranking"],
        }
        gold = set(row["gold_evidence_chunk_ids"])
        per_query.append({
            "annotation_id": row["annotation_id"],
            "query_slice": row["query_slice"],
            "query": row["query"],
            "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
            "metrics": {variant: metric_row(rankings[variant], gold) for variant in VARIANTS},
            "rankings": rankings,
            "adaptive_audit": adaptive_rank(retrieval, selected_parameters)["audit"],
        })

    aggregate_metrics = {
        variant: aggregate([row["metrics"][variant] for row in per_query])
        for variant in VARIANTS
    }
    uncertainty = {
        variant: {
            metric: mean_ci(
                [row["metrics"][variant][metric] for row in per_query],
                args.bootstrap_iterations,
                args.seed,
                f"heldout:{variant}:{metric}",
            )
            for metric in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
        }
        for variant in VARIANTS
    }
    families = {
        "adaptive_vs_text_rrf": ("adaptive_full", "text_rrf"),
        "incremental_graph_contribution": ("adaptive_full", "adaptive_without_graph"),
    }
    paired_comparisons = {}
    for family, (treatment, baseline) in families.items():
        comparisons = {
            metric: paired_test(
                [row["metrics"][treatment][metric] for row in per_query],
                [row["metrics"][baseline][metric] for row in per_query],
                metric,
                args.bootstrap_iterations,
                args.seed,
                f"heldout:{family}:{metric}",
            )
            for metric in ("hit_at_5", "mrr", "ndcg_at_5")
        }
        adjust_holm(comparisons)
        paired_comparisons[family] = comparisons

    by_slice = {}
    for query_slice in sorted({row["query_slice"] for row in per_query}):
        slice_rows = [row for row in per_query if row["query_slice"] == query_slice]
        by_slice[query_slice] = {
            variant: aggregate([row["metrics"][variant] for row in slice_rows])
            for variant in VARIANTS
        }
    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "formal_metrics": True,
        "query_count": len(per_query),
        "variants": list(VARIANTS),
        "selected_parameters": selected_parameters.__dict__,
        "aggregate": aggregate_metrics,
        "uncertainty": uncertainty,
        "by_slice": by_slice,
        "paired_comparisons": paired_comparisons,
        "input_hashes": {
            "pack": sha256_file(pack_path),
            "retrieval": sha256_file(retrieval_path),
            "development_report": sha256_file(development_report_path),
            "evaluation_code": sha256_file(Path(__file__)),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    per_query_path.write_text(json.dumps(per_query, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "query_count": len(per_query), "aggregate": aggregate_metrics}, indent=2))


if __name__ == "__main__":
    main()
