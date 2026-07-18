from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .common import read_json, sha256_file, write_json
from .config import BOOTSTRAP_ITERATIONS, BOOTSTRAP_SEED, METHODS
from .core import load_graph


METRIC_NAMES = ("hit_at_1", "hit_at_3", "hit_at_5", "mrr")


def metric_row(ranking: list[str], gold_signature: str) -> dict[str, float | int | None]:
    try:
        rank = ranking.index(gold_signature) + 1
    except ValueError:
        rank = None
    return {
        "rank": rank,
        "hit_at_1": float(rank is not None and rank <= 1),
        "hit_at_3": float(rank is not None and rank <= 3),
        "hit_at_5": float(rank is not None and rank <= 5),
        "mrr": 0.0 if rank is None else 1.0 / rank,
    }


def metric_from_rank(rank: int | None) -> dict[str, float | int | None]:
    return {
        "rank": rank,
        "hit_at_1": float(rank is not None and rank <= 1),
        "hit_at_3": float(rank is not None and rank <= 3),
        "hit_at_5": float(rank is not None and rank <= 5),
        "mrr": 0.0 if rank is None else 1.0 / rank,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot aggregate empty rows")
    return {name: float(np.mean([row[name] for row in rows])) for name in METRIC_NAMES}


def stratified_bootstrap(
    per_query: list[dict[str, Any]], treatment: str, control: str, metric: str
) -> dict[str, float]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in per_query:
        by_category[row["category"]].append(row)
    if sorted(map(len, by_category.values())) != [10, 10, 10]:
        raise ValueError("bootstrap requires three fixed 10-question categories")
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    samples = np.empty(BOOTSTRAP_ITERATIONS, dtype=np.float64)
    ordered = [by_category[key] for key in sorted(by_category)]
    for iteration in range(BOOTSTRAP_ITERATIONS):
        deltas = []
        for rows in ordered:
            indices = rng.integers(0, len(rows), size=len(rows))
            for index in indices:
                record = rows[int(index)]
                deltas.append(
                    float(record["metrics"][treatment][metric])
                    - float(record["metrics"][control][metric])
                )
        samples[iteration] = float(np.mean(deltas))
    observed = float(
        np.mean(
            [
                float(row["metrics"][treatment][metric])
                - float(row["metrics"][control][metric])
                for row in per_query
            ]
        )
    )
    return {
        "delta": observed,
        "ci_low": float(np.quantile(samples, 0.025)),
        "ci_high": float(np.quantile(samples, 0.975)),
    }


def ambiguity_audit(gold: dict[str, Any], graph: Any) -> list[dict[str, Any]]:
    findings = []
    for row in gold["questions"]:
        gold_keys = {
            (edge["source"], edge["relation"], edge["target"]) for edge in row["gold_edges"]
        }
        alternatives = []
        for source, relation, _ in sorted(gold_keys):
            for key in graph.adjacency.get(source, ()):
                if key[0] == source and key[1] == relation and key not in gold_keys:
                    alternatives.append(list(key))
        if alternatives:
            findings.append(
                {
                    "review_id": row["review_id"],
                    "final_question": row["final_question"],
                    "non_gold_same_source_relation_edges": sorted(alternatives),
                    "note": (
                        "Potential alternative answer or extra branch; inspect question wording. "
                        "This audit does not automatically change Gold."
                    ),
                }
            )
    return findings


def evaluate(
    gold: dict[str, Any],
    rankings: dict[str, Any],
    ranking_dir: Path,
    graph: Any,
    method_lock_path: Path,
) -> dict[str, Any]:
    if rankings.get("method_lock_sha256") != sha256_file(method_lock_path):
        raise ValueError("ranking output does not match method lock")
    gold_by_id = {row["review_id"]: row for row in gold.get("questions", [])}
    ranking_by_id = {row["review_id"]: row for row in rankings.get("query_files", [])}
    if len(gold_by_id) != 30 or set(gold_by_id) != set(ranking_by_id):
        raise ValueError("Gold and rankings must contain the same 30 questions")
    per_query = []
    sensitivity = []
    for review_id in sorted(gold_by_id):
        gold_row = gold_by_id[review_id]
        ranking_file_row = ranking_by_id[review_id]
        ranking_path = ranking_dir / ranking_file_row["file"]
        if sha256_file(ranking_path) != ranking_file_row["sha256"]:
            raise ValueError(f"ranking file hash mismatch: {ranking_path}")
        ranking_row = read_json(ranking_path)
        final_variant = ranking_row["variants"]["final"]
        gold_candidate_id = hashlib.sha256(
            gold_row["gold_signature"].encode("utf-8")
        ).hexdigest()
        rank_record = final_variant["rank_positions"].get(gold_candidate_id, {})
        metrics = {
            method: metric_from_rank(rank_record.get(method))
            for method in METHODS
        }
        per_query.append(
            {
                "review_id": review_id,
                "category": gold_row["category"],
                "wording_changed": gold_row["wording_changed"],
                "candidate_count": final_variant["candidate_count"],
                "candidate_cap_reached": final_variant["candidate_cap_reached"],
                "work_limit_aborted": final_variant["work_limit_aborted"],
                "anchor_count": len(final_variant["anchor_matches"]),
                "gold_generated": any(row["rank"] is not None for row in metrics.values()),
                "metrics": metrics,
            }
        )
        if gold_row["wording_changed"]:
            original_variant = ranking_row["variants"]["original"]
            original_rank_record = original_variant["rank_positions"].get(gold_candidate_id, {})
            sensitivity.append(
                {
                    "review_id": review_id,
                    "category": gold_row["category"],
                    "final_question": gold_row["final_question"],
                    "original_question": gold_row["original_question"],
                    "final": metrics,
                    "original": {
                        method: metric_from_rank(original_rank_record.get(method))
                        for method in METHODS
                    },
                }
            )

    aggregate_rows = {
        method: aggregate([row["metrics"][method] for row in per_query]) for method in METHODS
    }
    categories = sorted({row["category"] for row in per_query})
    by_category = {
        category: {
            method: aggregate(
                [row["metrics"][method] for row in per_query if row["category"] == category]
            )
            for method in METHODS
        }
        for category in categories
    }
    comparisons = {}
    for control in ("b0", "m0", "cue_off", "direction_off"):
        comparisons[f"r1_minus_{control}"] = {
            metric: stratified_bootstrap(per_query, "r1", control, metric)
            for metric in METRIC_NAMES
        }
    return {
        "schema_version": "1.0",
        "status": "feedback_driven_exploratory_graph_chain_evaluation_complete",
        "query_count": 30,
        "candidate_generation_recall": float(np.mean([row["gold_generated"] for row in per_query])),
        "candidate_cap_count": sum(row["candidate_cap_reached"] for row in per_query),
        "work_limit_abort_count": sum(row["work_limit_aborted"] for row in per_query),
        "anchor_failure_count": sum(row["anchor_count"] == 0 for row in per_query),
        "aggregate": aggregate_rows,
        "by_category": by_category,
        "paired_bootstrap": comparisons,
        "wording_sensitivity": sensitivity,
        "ambiguity_audit": ambiguity_audit(gold, graph),
        "per_query": per_query,
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Exploratory relation-aware graph evidence-chain ranking",
        "",
        "This experiment was added after project-group feedback and is exploratory, not confirmatory.",
        "",
        f"- Questions: {result['query_count']}",
        f"- Candidate-generation recall: {result['candidate_generation_recall']:.3f}",
        f"- Candidate-cap queries: {result['candidate_cap_count']}",
        f"- Work-limit aborts: {result['work_limit_abort_count']}",
        f"- Anchor failures: {result['anchor_failure_count']}",
        "",
        "## Overall",
        "",
        "| Method | Hit@1 | Hit@3 | Hit@5 | MRR |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        row = result["aggregate"][method]
        lines.append(
            f"| {method} | {row['hit_at_1']:.3f} | {row['hit_at_3']:.3f} | "
            f"{row['hit_at_5']:.3f} | {row['mrr']:.3f} |"
        )
    lines.extend(["", "## Category slices", ""])
    for category, methods in result["by_category"].items():
        lines.extend(
            [
                f"### {category}",
                "",
                "| Method | Hit@1 | Hit@3 | Hit@5 | MRR |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for method in METHODS:
            row = methods[method]
            lines.append(
                f"| {method} | {row['hit_at_1']:.3f} | {row['hit_at_3']:.3f} | "
                f"{row['hit_at_5']:.3f} | {row['mrr']:.3f} |"
            )
        lines.append("")
    lines.extend(["## R1 paired differences", ""])
    for comparison, metrics in result["paired_bootstrap"].items():
        lines.append(f"### {comparison}")
        lines.append("")
        for metric, interval in metrics.items():
            lines.append(
                f"- {metric}: {interval['delta']:.3f} "
                f"(95% percentile interval {interval['ci_low']:.3f}, {interval['ci_high']:.3f})"
            )
        lines.append("")
    lines.extend(
        [
            "## Limitations",
            "",
            "The questions were constructed from known graph relations. The experiment therefore "
            "tests ranking within a declared supply/regulatory graph view and does not estimate "
            "performance on arbitrary unseen graph questions. Ambiguity-audit findings must be "
            "inspected before manuscript reporting.",
            "",
        ]
    )
    if result["ambiguity_audit"]:
        lines.extend(["## Ambiguity audit", ""])
        for row in result["ambiguity_audit"]:
            lines.append(
                f"- {row['review_id']}: {len(row['non_gold_same_source_relation_edges'])} "
                "same-source/relation non-Gold edge(s)."
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--method-lock", type=Path, required=True)
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        read_json(args.gold),
        read_json(args.rankings),
        args.rankings.parent,
        load_graph(args.nodes, args.edges),
        args.method_lock,
    )
    write_json(args.output_json, result)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    if args.output_md.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output_md}")
    args.output_md.write_text(markdown_report(result), encoding="utf-8")
    print(f"evaluation complete: {args.output_json}")


if __name__ == "__main__":
    main()
