"""Select and audit adaptive text-first parameters on the 60-query development set."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adaptive_text_first import AdaptiveParameters, adaptive_rank
from analyze_three_path_ablation import mean_ci, paired_test
from statsmodels.stats.multitest import multipletests
from three_path_evaluation import hit_at_k, ndcg_at_k, reciprocal_rank, validate_frozen_pack


DEFAULT_EVAL = Path("data/eval/three_path_evaluation_frozen_2026-07-15.json")
DEFAULT_RETRIEVAL = Path("artifacts/three_path_retrieval/formal_frozen_2026-07-15/per_query.json")
DEFAULT_OUTPUT = Path("outputs/adaptive_text_first_development_2026-07-15")
GRID = {
    "explicit_document_boost": (0.0, 0.004, 0.008),
    "table_boost": (0.0, 0.004, 0.008),
    "heading_overlap_boost": (0.0, 0.003),
    "graph_weight": (0.0, 0.25, 0.5),
    "retain_text_top_n": (0, 1),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(ranking: list[str], gold: set[str]) -> dict[str, float]:
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


def parameter_grid() -> list[AdaptiveParameters]:
    names = list(GRID)
    return [
        AdaptiveParameters(**dict(zip(names, values, strict=True)))
        for values in itertools.product(*(GRID[name] for name in names))
    ]


def selection_key(row: dict[str, Any]) -> tuple[Any, ...]:
    metrics_row = row["metrics"]
    parameters = row["parameters"]
    complexity = sum(
        bool(parameters[name])
        for name in ("explicit_document_boost", "table_boost", "heading_overlap_boost", "graph_weight", "retain_text_top_n")
    )
    return (
        -metrics_row["hit_at_5"],
        -metrics_row["mrr"],
        -metrics_row["ndcg_at_5"],
        row["graph_enabled_queries"],
        complexity,
        parameters["graph_weight"],
        parameters["explicit_document_boost"],
        parameters["table_boost"],
        parameters["heading_overlap_boost"],
        parameters["retain_text_top_n"],
    )


def markdown_report(report: dict[str, Any]) -> str:
    baseline = report["baseline"]["metrics"]
    selected = report["selected"]["metrics"]
    params = report["selected"]["parameters"]
    lines = [
        "# Adaptive Text-First Development Report",
        "",
        "This report uses only the frozen 60-query development set. The 30-query held-out set was not executed.",
        "",
        "## Results",
        "",
        "| Method | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Text RRF baseline | {baseline['hit_at_1']:.3f} | {baseline['hit_at_3']:.3f} | {baseline['hit_at_5']:.3f} | {baseline['mrr']:.3f} | {baseline['ndcg_at_5']:.3f} |",
        f"| Selected adaptive | {selected['hit_at_1']:.3f} | {selected['hit_at_3']:.3f} | {selected['hit_at_5']:.3f} | {selected['mrr']:.3f} | {selected['ndcg_at_5']:.3f} |",
        "",
        "All metric means and bootstrap intervals are available in `development_report.json`; selected headline intervals are:",
        "",
    ]
    for metric in ("hit_at_5", "mrr", "ndcg_at_5"):
        base_ci = report["baseline"]["uncertainty"][metric]
        selected_ci = report["selected"]["uncertainty"][metric]
        lines.append(
            f"- {metric}: baseline {base_ci['mean']:.4f} [{base_ci['ci_95_low']:.4f}, {base_ci['ci_95_high']:.4f}]; "
            f"adaptive {selected_ci['mean']:.4f} [{selected_ci['ci_95_low']:.4f}, {selected_ci['ci_95_high']:.4f}]."
        )
    lines.extend([
        "",
        "## Selected parameters",
        "",
        "```json",
        json.dumps(params, indent=2),
        "```",
        "",
        f"Grid configurations evaluated: {report['grid_configuration_count']}.",
        f"Graph gate enabled for {report['selected']['graph_enabled_queries']} of 60 development queries.",
        f"Route-retention actions applied: {report['selected']['retention_action_count']}.",
        "",
        "## Paired development comparisons",
        "",
    ])
    for metric, comparison in report["paired_comparisons"].items():
        lines.append(
            f"- {metric}: delta {comparison['delta_mean']:.4f}, 95% CI "
            f"[{comparison['delta_ci_95_low']:.4f}, {comparison['delta_ci_95_high']:.4f}], "
            f"raw p={comparison['p_value_raw']:.4g}, Holm p={comparison['p_value_holm']:.4g}."
        )
    lines.extend([
        "",
        "Development comparisons are descriptive after parameter selection and are not confirmatory evidence.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", default=str(DEFAULT_EVAL))
    parser.add_argument("--retrieval", default=str(DEFAULT_RETRIEVAL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    evaluation_path = Path(args.evaluation)
    retrieval_path = Path(args.retrieval)
    output_dir = Path(args.output)
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite existing development output: {output_dir}")
    output_dir.mkdir(parents=True)

    evaluation_rows = validate_frozen_pack(read_json(evaluation_path))
    retrieval_records = read_json(retrieval_path)
    retrieval_by_query = {str(record["retrieval"]["query"]): record["retrieval"] for record in retrieval_records}
    if len(retrieval_by_query) != len(retrieval_records):
        raise ValueError("duplicate retrieval queries in development artifact")
    missing = [row["annotation_id"] for row in evaluation_rows if row["query"] not in retrieval_by_query]
    if missing:
        raise ValueError(f"development retrieval is missing queries: {missing}")

    grid_results: list[dict[str, Any]] = []
    detailed_by_parameter: dict[str, list[dict[str, Any]]] = {}
    for grid_index, parameters in enumerate(parameter_grid()):
        per_query = []
        graph_enabled = 0
        retention_actions = 0
        for row in evaluation_rows:
            result = adaptive_rank(retrieval_by_query[row["query"]], parameters)
            metric_row = metrics(result["ranking"], set(row["gold_evidence_chunk_ids"]))
            graph_enabled += int(result["audit"]["graph_gate"]["enabled"] and parameters.graph_weight > 0)
            retention_actions += len(result["audit"]["retention_actions"])
            per_query.append({
                "annotation_id": row["annotation_id"],
                "query_slice": row["query_slice"],
                "query": row["query"],
                "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
                "metrics": metric_row,
                "adaptive": result,
            })
        key = f"grid_{grid_index:03d}"
        grid_results.append({
            "grid_id": key,
            "parameters": asdict(parameters),
            "metrics": aggregate([row["metrics"] for row in per_query]),
            "graph_enabled_queries": graph_enabled,
            "retention_action_count": retention_actions,
        })
        detailed_by_parameter[key] = per_query

    baseline_parameters = AdaptiveParameters(
        graph_weight=0.0,
        explicit_document_boost=0.0,
        table_boost=0.0,
        heading_overlap_boost=0.0,
        retain_text_top_n=0,
    )
    baseline = next(row for row in grid_results if row["parameters"] == asdict(baseline_parameters))
    selected = min(grid_results, key=selection_key)
    selected_rows = detailed_by_parameter[selected["grid_id"]]
    baseline_rows = detailed_by_parameter[baseline["grid_id"]]

    selected_uncertainty = {
        name: mean_ci(
            [row["metrics"][name] for row in selected_rows],
            args.bootstrap_iterations,
            args.seed,
            f"selected:{name}",
        )
        for name in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
    }
    baseline_uncertainty = {
        name: mean_ci(
            [row["metrics"][name] for row in baseline_rows],
            args.bootstrap_iterations,
            args.seed,
            f"baseline:{name}",
        )
        for name in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
    }
    comparisons = {
        name: paired_test(
            [row["metrics"][name] for row in selected_rows],
            [row["metrics"][name] for row in baseline_rows],
            name,
            args.bootstrap_iterations,
            args.seed,
            f"selected_vs_text_rrf:{name}",
        )
        for name in ("hit_at_5", "mrr", "ndcg_at_5")
    }
    rejected, adjusted_p, _alpha_sidak, _alpha_bonf = multipletests(
        [comparison["p_value_raw"] for comparison in comparisons.values()],
        alpha=0.05,
        method="holm",
    )
    for comparison, corrected, is_rejected in zip(comparisons.values(), adjusted_p, rejected, strict=True):
        comparison["p_value_holm"] = round(float(corrected), 8)
        comparison["significant_after_holm_0_05"] = bool(is_rejected)

    text_route_retention_violations = []
    for evaluation_row, selected_row in zip(evaluation_rows, selected_rows, strict=True):
        retrieval = retrieval_by_query[evaluation_row["query"]]
        bottom_ids = {str(item["chunk_id"]) for item in (retrieval.get("bottom_up") or [])[:5]}
        top_ids = {str(item["chunk_id"]) for item in ((retrieval.get("top_down") or {}).get("evidence") or [])[:5]}
        gold = set(evaluation_row["gold_evidence_chunk_ids"])
        component_hit = bool(gold & (bottom_ids | top_ids))
        adaptive_hit = bool(gold & set(selected_row["adaptive"]["top_k"]))
        if component_hit and not adaptive_hit:
            text_route_retention_violations.append(evaluation_row["annotation_id"])
    if text_route_retention_violations:
        raise AssertionError(f"adaptive fusion removed text-route Top-5 Gold evidence: {text_route_retention_violations}")

    baseline_expected = {"hit_at_5": 0.833333, "mrr": 0.607083, "ndcg_at_5": 0.578702}
    baseline_matches = all(baseline["metrics"][name] == value for name, value in baseline_expected.items())
    hit_monotonic = all(
        row["metrics"]["hit_at_1"] <= row["metrics"]["hit_at_3"] <= row["metrics"]["hit_at_5"]
        for row in selected_rows
    )
    bounded_intervals = all(
        0.0 <= interval["ci_95_low"] <= interval["mean"] <= interval["ci_95_high"] <= 1.0
        for method in (selected_uncertainty, baseline_uncertainty)
        for interval in method.values()
    )
    quality_checks = {
        "baseline_matches_prior_ablation": baseline_matches,
        "text_route_top5_retention_violation_count": len(text_route_retention_violations),
        "hit_at_k_monotonic_per_query": hit_monotonic,
        "bootstrap_intervals_bounded": bounded_intervals,
        "development_query_count": len(selected_rows),
        "grid_configuration_count": len(grid_results),
    }
    if not baseline_matches or not hit_monotonic or not bounded_intervals or len(selected_rows) != 60 or len(grid_results) != 108:
        raise AssertionError(f"development quality gate failed: {quality_checks}")
    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dataset_role": "development_only_not_heldout",
        "heldout_executed": False,
        "selection_rule": "maximize Hit@5, MRR, nDCG@5; then minimize graph-enabled queries, nonzero parameter count, and parameter values",
        "grid": GRID,
        "grid_configuration_count": len(grid_results),
        "baseline": {**baseline, "uncertainty": baseline_uncertainty},
        "selected": {**selected, "uncertainty": selected_uncertainty},
        "paired_comparisons": comparisons,
        "quality_checks": quality_checks,
        "input_hashes": {
            "evaluation": sha256_file(evaluation_path),
            "retrieval": sha256_file(retrieval_path),
            "adaptive_code": sha256_file(Path(__file__).with_name("adaptive_text_first.py")),
        },
    }
    (output_dir / "grid_results.json").write_text(json.dumps(grid_results, indent=2), encoding="utf-8")
    (output_dir / "selected_per_query.json").write_text(json.dumps(selected_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "development_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "development_report.md").write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({
        "output": str(output_dir),
        "grid_configuration_count": len(grid_results),
        "baseline": baseline["metrics"],
        "selected": selected,
        "paired_comparisons": comparisons,
    }, indent=2))


if __name__ == "__main__":
    main()
