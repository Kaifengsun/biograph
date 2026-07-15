"""Post-hoc ablation and paired statistical analysis on a frozen retrieval run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.stats import binomtest, wilcoxon
from statsmodels.stats.multitest import multipletests

from build_regulatory_evidence_graph import normalize_alias
from three_path_evaluation import (
    hit_at_k,
    ndcg_at_k,
    ranked_chunk_ids,
    reciprocal_rank,
    sha256_file,
    validate_frozen_pack,
)


VARIANT_COMPONENTS = {
    "bottom_up": ("bottom_up",),
    "top_down": ("top_down",),
    "graph_path": ("graph_path",),
    "bottom_up_top_down_rrf": ("bottom_up", "top_down"),
    "bottom_up_graph_rrf": ("bottom_up", "graph_path"),
    "top_down_graph_rrf": ("top_down", "graph_path"),
    "three_path_rrf": ("bottom_up", "top_down", "graph_path"),
}

METRICS = ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
PRIMARY_COMPARISONS = (
    ("three_path_rrf", "bottom_up_top_down_rrf", "incremental_graph_contribution"),
    ("bottom_up_top_down_rrf", "top_down", "incremental_text_fusion_contribution"),
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def chunk_document_map(corpus: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(corpus.glob("*_enriched.json")):
        for row in read_json(path):
            chunk_id = str(row.get("chunk_id", ""))
            if chunk_id:
                result[chunk_id] = str(row.get("doc_id", ""))
    if not result:
        raise ValueError(f"no frozen chunks found in corpus: {corpus}")
    return result


def corpus_fingerprint(corpus: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(corpus.glob("*_enriched.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def rrf_rank(rankings: Iterable[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    first_rank: dict[str, int] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, 1):
            scores[chunk_id] += 1.0 / (k + rank)
            first_rank[chunk_id] = min(first_rank.get(chunk_id, rank), rank)
    return [
        chunk_id
        for chunk_id, _score in sorted(
            scores.items(), key=lambda item: (-item[1], first_rank[item[0]], item[0])
        )
    ]


def variant_rankings(retrieval: dict[str, Any]) -> dict[str, list[str]]:
    components = {
        name: ranked_chunk_ids(retrieval, name)
        for name in ("bottom_up", "top_down", "graph_path")
    }
    result = {}
    for variant, names in VARIANT_COMPONENTS.items():
        result[variant] = components[names[0]] if len(names) == 1 else rrf_rank(components[name] for name in names)
    return result


def metric_row(ranking: list[str], gold: set[str]) -> dict[str, float]:
    return {
        "hit_at_1": hit_at_k(ranking, gold, 1),
        "hit_at_3": hit_at_k(ranking, gold, 3),
        "hit_at_5": hit_at_k(ranking, gold, 5),
        "mrr": reciprocal_rank(ranking, gold),
        "ndcg_at_5": ndcg_at_k(ranking, gold, 5),
    }


def stable_seed(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def mean_ci(values: Iterable[float], iterations: int, seed: int, label: str) -> dict[str, float | int]:
    array = np.asarray(list(values), dtype=float)
    if not len(array):
        return {"n": 0, "mean": None, "ci_95_low": None, "ci_95_high": None}
    rng = np.random.default_rng(stable_seed(seed, label))
    indices = rng.integers(0, len(array), size=(iterations, len(array)))
    means = array[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "n": int(len(array)),
        "mean": round(float(array.mean()), 6),
        "ci_95_low": round(float(low), 6),
        "ci_95_high": round(float(high), 6),
    }


def paired_test(
    treatment: Iterable[float],
    baseline: Iterable[float],
    metric: str,
    iterations: int,
    seed: int,
    label: str,
) -> dict[str, Any]:
    treatment_array = np.asarray(list(treatment), dtype=float)
    baseline_array = np.asarray(list(baseline), dtype=float)
    if treatment_array.shape != baseline_array.shape or not len(treatment_array):
        raise ValueError("paired test requires equal non-empty arrays")
    differences = treatment_array - baseline_array
    delta = mean_ci(differences, iterations, seed, f"{label}:delta")
    if metric.startswith("hit_at_"):
        improvements = int(np.sum((treatment_array == 1) & (baseline_array == 0)))
        regressions = int(np.sum((treatment_array == 0) & (baseline_array == 1)))
        discordant = improvements + regressions
        p_value = float(binomtest(improvements, discordant, p=0.5, alternative="two-sided").pvalue) if discordant else 1.0
        details = {
            "test": "exact_paired_mcnemar_binomial",
            "improvements": improvements,
            "regressions": regressions,
            "discordant_pairs": discordant,
        }
    else:
        nonzero = differences[~np.isclose(differences, 0.0)]
        if len(nonzero):
            statistic, p_value = wilcoxon(
                treatment_array,
                baseline_array,
                zero_method="wilcox",
                correction=False,
                alternative="two-sided",
                method="auto",
            )
            statistic = float(statistic)
            p_value = float(p_value)
        else:
            statistic, p_value = 0.0, 1.0
        details = {
            "test": "paired_wilcoxon_signed_rank",
            "statistic": statistic,
            "nonzero_pairs": int(len(nonzero)),
        }
    return {
        "metric": metric,
        "delta_mean": delta["mean"],
        "delta_ci_95_low": delta["ci_95_low"],
        "delta_ci_95_high": delta["ci_95_high"],
        "p_value_raw": round(p_value, 8),
        **details,
    }


def first_gold_rank(ranking: list[str], gold: set[str]) -> int | None:
    for rank, chunk_id in enumerate(ranking, 1):
        if chunk_id in gold:
            return rank
    return None


def build_analysis(
    frozen: dict[str, Any],
    retrieval_rows: list[dict[str, Any]],
    chunk_docs: dict[str, str],
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    frozen_rows = validate_frozen_pack(frozen)
    retrieval_by_query: dict[str, dict[str, Any]] = {}
    for record in retrieval_rows:
        retrieval = record.get("retrieval") or {}
        key = normalize_alias(str(retrieval.get("query", "")))
        if not key or key in retrieval_by_query:
            raise ValueError(f"missing or duplicate retrieval query: {retrieval.get('query')!r}")
        retrieval_by_query[key] = retrieval

    per_query = []
    for row in frozen_rows:
        retrieval = retrieval_by_query.get(normalize_alias(str(row["query"])))
        if retrieval is None:
            raise ValueError(f"missing retrieval result for {row['annotation_id']}")
        gold = set(row["gold_evidence_chunk_ids"])
        rankings = variant_rankings(retrieval)
        metrics = {variant: metric_row(ranking, gold) for variant, ranking in rankings.items()}
        per_query.append({
            "annotation_id": row["annotation_id"],
            "query_slice": row["query_slice"],
            "query": row["query"],
            "gold_evidence_chunk_ids": sorted(gold),
            "rankings": rankings,
            "first_gold_rank": {variant: first_gold_rank(ranking, gold) for variant, ranking in rankings.items()},
            "metrics": metrics,
        })

    aggregate = {
        variant: {
            metric: mean_ci(
                (row["metrics"][variant][metric] for row in per_query),
                iterations,
                seed,
                f"aggregate:{variant}:{metric}",
            )
            for metric in METRICS
        }
        for variant in VARIANT_COMPONENTS
    }
    by_slice = {}
    for query_slice in sorted({row["query_slice"] for row in per_query}):
        subset = [row for row in per_query if row["query_slice"] == query_slice]
        by_slice[query_slice] = {
            variant: {
                metric: mean_ci(
                    (row["metrics"][variant][metric] for row in subset),
                    iterations,
                    seed,
                    f"slice:{query_slice}:{variant}:{metric}",
                )
                for metric in METRICS
            }
            for variant in VARIANT_COMPONENTS
        }
        by_slice[query_slice]["three_path_minus_text_hit_at_5"] = mean_ci(
            (
                row["metrics"]["three_path_rrf"]["hit_at_5"]
                - row["metrics"]["bottom_up_top_down_rrf"]["hit_at_5"]
                for row in subset
            ),
            iterations,
            seed,
            f"slice:{query_slice}:three_path_minus_text:hit_at_5",
        )

    comparisons = []
    for treatment, baseline, hypothesis in PRIMARY_COMPARISONS:
        group = []
        for metric in METRICS:
            result = paired_test(
                (row["metrics"][treatment][metric] for row in per_query),
                (row["metrics"][baseline][metric] for row in per_query),
                metric,
                iterations,
                seed,
                f"comparison:{hypothesis}:{metric}",
            )
            result.update({"treatment": treatment, "baseline": baseline, "hypothesis": hypothesis})
            group.append(result)
        adjusted = multipletests([row["p_value_raw"] for row in group], alpha=0.05, method="holm")
        for row, rejected, adjusted_p in zip(group, adjusted[0], adjusted[1]):
            row["p_value_holm"] = round(float(adjusted_p), 8)
            row["significant_after_holm_0_05"] = bool(rejected)
        comparisons.extend(group)

    graph_effect = Counter()
    graph_effect_rows = []
    for row in per_query:
        text_hit = int(row["metrics"]["bottom_up_top_down_rrf"]["hit_at_5"])
        full_hit = int(row["metrics"]["three_path_rrf"]["hit_at_5"])
        if full_hit > text_hit:
            effect = "helped_at_5"
        elif full_hit < text_hit:
            effect = "hurt_at_5"
        else:
            effect = "unchanged_at_5"
        graph_effect[effect] += 1
        if effect != "unchanged_at_5":
            graph_effect_rows.append({
                "annotation_id": row["annotation_id"],
                "query_slice": row["query_slice"],
                "query": row["query"],
                "effect": effect,
                "text_first_gold_rank": row["first_gold_rank"]["bottom_up_top_down_rrf"],
                "full_first_gold_rank": row["first_gold_rank"]["three_path_rrf"],
            })

    full_failures = []
    failure_counts: Counter[str] = Counter()
    for row in per_query:
        if row["metrics"]["three_path_rrf"]["hit_at_5"]:
            continue
        retrieval = retrieval_by_query[normalize_alias(str(row["query"]))]
        gold_docs = sorted({chunk_docs.get(chunk_id, "") for chunk_id in row["gold_evidence_chunk_ids"]} - {""})
        selected_docs = list((retrieval.get("top_down") or {}).get("selected_documents") or [])
        component_hit = any(
            row["first_gold_rank"][variant] is not None and row["first_gold_rank"][variant] <= 5
            for variant in ("bottom_up", "top_down", "graph_path")
        )
        if component_hit:
            category = "fusion_rank_dilution"
        elif set(gold_docs) & set(selected_docs):
            category = "within_correct_document_chunk_ranking_miss"
        else:
            category = "document_routing_miss"
        failure_counts[category] += 1
        full_failures.append({
            "annotation_id": row["annotation_id"],
            "query_slice": row["query_slice"],
            "query": row["query"],
            "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
            "gold_document_ids": gold_docs,
            "top_down_selected_document_ids": selected_docs,
            "component_first_gold_ranks": {
                variant: row["first_gold_rank"][variant]
                for variant in ("bottom_up", "top_down", "graph_path")
            },
            "full_first_gold_rank": row["first_gold_rank"]["three_path_rrf"],
            "graph_abstained": bool((retrieval.get("graph_path") or {}).get("abstained")),
            "diagnostic_category": category,
        })
    return {
        "analysis_status": "post_hoc_ablation_on_frozen_human_reviewed_set",
        "query_count": len(per_query),
        "rrf_k": 60,
        "bootstrap": {"method": "paired_query_resampling_percentile", "iterations": iterations, "seed": seed, "confidence_level": 0.95},
        "multiple_comparisons": "Holm correction is applied separately across the five metrics within each named paired hypothesis.",
        "variant_components": {key: list(value) for key, value in VARIANT_COMPONENTS.items()},
        "aggregate": aggregate,
        "by_slice": by_slice,
        "paired_comparisons": comparisons,
        "graph_increment_at_hit_5": {"counts": dict(sorted(graph_effect.items())), "changed_queries": graph_effect_rows},
        "full_fusion_failures_at_5": {
            "counts": dict(sorted(failure_counts.items())),
            "queries": full_failures,
        },
        "per_query": per_query,
    }


def interval_text(summary: dict[str, Any]) -> str:
    return f"{summary['mean']:.3f} [{summary['ci_95_low']:.3f}, {summary['ci_95_high']:.3f}]"


def markdown_report(report: dict[str, Any]) -> str:
    labels = {
        "bottom_up": "Bottom-up",
        "top_down": "Top-down",
        "graph_path": "Graph path",
        "bottom_up_top_down_rrf": "Bottom-up + Top-down",
        "bottom_up_graph_rrf": "Bottom-up + Graph",
        "top_down_graph_rrf": "Top-down + Graph",
        "three_path_rrf": "Three-path RRF",
    }
    lines = [
        "# Three-Path Retrieval Ablation and Statistical Analysis",
        "",
        f"Frozen human-reviewed queries: {report['query_count']}",
        "",
        "This is a post-hoc ablation over immutable rankings from the frozen run. Values are means with query-bootstrap 95% confidence intervals.",
        "",
        "## Aggregate ablation",
        "",
        "| Variant | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for variant in VARIANT_COMPONENTS:
        values = report["aggregate"][variant]
        lines.append("| " + " | ".join([
            labels[variant],
            interval_text(values["hit_at_1"]),
            interval_text(values["hit_at_3"]),
            interval_text(values["hit_at_5"]),
            interval_text(values["mrr"]),
            interval_text(values["ndcg_at_5"]),
        ]) + " |")

    lines.extend([
        "",
        "## Paired comparisons",
        "",
        "| Hypothesis | Metric | Mean delta | 95% CI | Test | Raw p | Holm p | Significant |",
        "| --- | --- | ---: | --- | --- | ---: | ---: | --- |",
    ])
    for row in report["paired_comparisons"]:
        lines.append(
            f"| {row['hypothesis']} | {row['metric']} | {row['delta_mean']:.3f} | "
            f"[{row['delta_ci_95_low']:.3f}, {row['delta_ci_95_high']:.3f}] | {row['test']} | "
            f"{row['p_value_raw']:.4g} | {row['p_value_holm']:.4g} | "
            f"{'yes' if row['significant_after_holm_0_05'] else 'no'} |"
        )

    lines.extend([
        "",
        "## Hit@5 by query slice",
        "",
        "| Slice | n | Bottom-up + Top-down | Three-path RRF | Paired delta (95% CI) |",
        "| --- | ---: | --- | --- | --- |",
    ])
    for query_slice, values in report["by_slice"].items():
        text = values["bottom_up_top_down_rrf"]["hit_at_5"]
        full = values["three_path_rrf"]["hit_at_5"]
        delta = values["three_path_minus_text_hit_at_5"]
        lines.append(
            f"| {query_slice} | {full['n']} | {interval_text(text)} | {interval_text(full)} | "
            f"{delta['mean']:+.3f} [{delta['ci_95_low']:+.3f}, {delta['ci_95_high']:+.3f}] |"
        )

    effects = report["graph_increment_at_hit_5"]["counts"]
    lines.extend([
        "",
        "## Graph contribution at Hit@5",
        "",
        f"Graph fusion helped {effects.get('helped_at_5', 0)} queries, hurt {effects.get('hurt_at_5', 0)}, and left {effects.get('unchanged_at_5', 0)} unchanged relative to Bottom-up + Top-down RRF.",
        "",
        f"Full-fusion misses at rank 5: {len(report['full_fusion_failures_at_5']['queries'])}.",
        "",
        "## Failure diagnosis",
        "",
        "| Category | Count | Query IDs |",
        "| --- | ---: | --- |",
    ])
    failures_by_category: dict[str, list[str]] = defaultdict(list)
    for row in report["full_fusion_failures_at_5"]["queries"]:
        failures_by_category[row["diagnostic_category"]].append(row["annotation_id"])
    for category, count in report["full_fusion_failures_at_5"]["counts"].items():
        lines.append(f"| {category} | {count} | {', '.join(failures_by_category[category])} |")
    lines.extend([
        "",
        "The structured FDA nodes remain a separate graph-path validation modality and are not counted as text chunks in these metrics.",
        "Slice estimates with very small n, especially the single supply-chain query, are descriptive only.",
        "",
    ])
    return "\n".join(lines)


def write_per_query_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["annotation_id", "query_slice", "query"]
    for variant in VARIANT_COMPONENTS:
        fields.extend([f"{variant}_first_gold_rank", *(f"{variant}_{metric}" for metric in METRICS)])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat: dict[str, Any] = {key: row[key] for key in ("annotation_id", "query_slice", "query")}
            for variant in VARIANT_COMPONENTS:
                flat[f"{variant}_first_gold_rank"] = row["first_gold_rank"][variant]
                for metric in METRICS:
                    flat[f"{variant}_{metric}"] = row["metrics"][variant][metric]
            writer.writerow(flat)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze frozen three-path retrieval ablations")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--retrieval", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()
    pack_path = Path(args.pack)
    retrieval_path = Path(args.retrieval)
    corpus_path = Path(args.corpus)
    output = Path(args.output)
    markdown_output = output.with_suffix(".md")
    csv_output = output.with_name(f"{output.stem}-per-query.csv")
    if any(path.exists() for path in (output, markdown_output, csv_output)):
        raise RuntimeError("refusing to overwrite an existing ablation artifact")
    report = build_analysis(
        read_json(pack_path),
        read_json(retrieval_path),
        chunk_document_map(corpus_path),
        args.bootstrap_iterations,
        args.seed,
    )
    report["analysis"] = {
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pack": str(pack_path),
        "pack_sha256": sha256_file(pack_path),
        "retrieval": str(retrieval_path),
        "retrieval_sha256": sha256_file(retrieval_path),
        "corpus": str(corpus_path),
        "corpus_fingerprint": corpus_fingerprint(corpus_path),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(markdown_report(report), encoding="utf-8")
    write_per_query_csv(csv_output, report["per_query"])
    print(json.dumps({
        "query_count": report["query_count"],
        "output": str(output),
        "markdown": str(markdown_output),
        "per_query_csv": str(csv_output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
