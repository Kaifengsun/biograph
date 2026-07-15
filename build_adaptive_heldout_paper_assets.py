"""Audit locked held-out results and generate paper-ready Markdown and LaTeX tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_FORMAL = Path("outputs/adaptive_text_first_heldout_2026-07-15/formal_evaluation.json")
DEFAULT_PER_QUERY = Path("outputs/adaptive_text_first_heldout_2026-07-15/formal_evaluation-per-query.json")
DEFAULT_GRAPH = Path("outputs/adaptive_text_first_heldout_2026-07-15/three_path_validation.json")
DEFAULT_LOCK = Path("outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json")
DEFAULT_OUTPUT = Path("outputs/adaptive_text_first_heldout_2026-07-15/paper_ready")

VARIANT_LABELS = {
    "bottom_up": "Bottom-up",
    "top_down": "Top-down",
    "graph_path": "Graph path",
    "text_rrf": "Bottom-up + Top-down RRF",
    "unconditional_three_path_rrf": "Unconditional three-path RRF",
    "adaptive_without_graph": "Adaptive without graph",
    "adaptive_full": "Full adaptive text-first",
}
METRICS = ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latex_escape(value: str) -> str:
    return value.replace("&", r"\&").replace("_", r"\_")


def overall_latex(formal: dict[str, Any]) -> str:
    aggregate = formal["aggregate"]
    best = {metric: max(aggregate[variant][metric] for variant in aggregate) for metric in METRICS}
    rows = []
    for variant in formal["variants"]:
        values = []
        for metric in METRICS:
            rendered = f"{aggregate[variant][metric]:.3f}"
            if aggregate[variant][metric] == best[metric]:
                rendered = rf"\textbf{{{rendered}}}"
            values.append(rendered)
        rows.append(f"{latex_escape(VARIANT_LABELS[variant])} & " + " & ".join(values) + r" \\")
    return "\n".join([
        r"\begin{table*}[t]",
        r"\centering",
        r"\begin{threeparttable}",
        r"\caption{Held-out retrieval performance on 30 human-reviewed queries.}",
        r"\label{tab:adaptive-heldout-overall}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Method & Hit@1 & Hit@3 & Hit@5 & MRR & nDCG@5 \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}[flushleft]\footnotesize",
        r"\item Bold indicates the best value; ties are retained. Graph-path node-chain validation is evaluated separately from text-chunk retrieval.",
        r"\end{tablenotes}",
        r"\end{threeparttable}",
        r"\end{table*}",
        "",
    ])


def slice_latex(formal: dict[str, Any]) -> str:
    variants = ("bottom_up", "top_down", "text_rrf", "adaptive_full")
    slices = list(formal["by_slice"])
    rows = []
    for query_slice in slices:
        values = [formal["by_slice"][query_slice][variant]["hit_at_5"] for variant in variants]
        best = max(values)
        rendered = [rf"\textbf{{{value:.3f}}}" if value == best else f"{value:.3f}" for value in values]
        rows.append(f"{latex_escape(query_slice.replace('_', ' ').title())} & " + " & ".join(rendered) + r" \\")
    return "\n".join([
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Held-out Hit@5 by query slice.}",
        r"\label{tab:adaptive-heldout-slices}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Slice & Bottom-up & Top-down & Text RRF & Adaptive \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ])


def markdown_report(summary: dict[str, Any], formal: dict[str, Any]) -> str:
    aggregate = formal["aggregate"]
    lines = [
        "# Adaptive Text-First Held-Out Results",
        "",
        "## Overall retrieval",
        "",
        "| Method | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in formal["variants"]:
        row = aggregate[variant]
        lines.append(
            f"| {VARIANT_LABELS[variant]} | {row['hit_at_1']:.3f} | {row['hit_at_3']:.3f} | "
            f"{row['hit_at_5']:.3f} | {row['mrr']:.3f} | {row['ndcg_at_5']:.3f} |"
        )
    comparison = formal["paired_comparisons"]["adaptive_vs_text_rrf"]
    graph_comparison = formal["paired_comparisons"]["incremental_graph_contribution"]
    lines.extend([
        "",
        "## Statistical interpretation",
        "",
        f"Adaptive text-first improved Hit@5 over text RRF by {comparison['hit_at_5']['delta_mean']:.3f} "
        f"(95% CI [{comparison['hit_at_5']['delta_ci_95_low']:.3f}, {comparison['hit_at_5']['delta_ci_95_high']:.3f}], "
        f"Holm p={comparison['hit_at_5']['p_value_holm']:.3f}); this difference is not statistically significant.",
        f"The adaptive method tied the strongest single-route Top-down baseline at Hit@5 ({aggregate['adaptive_full']['hit_at_5']:.3f}) "
        f"and improved MRR descriptively from {aggregate['top_down']['mrr']:.3f} to {aggregate['adaptive_full']['mrr']:.3f}.",
        f"Adaptive graph contribution to text ranking was exactly {graph_comparison['hit_at_5']['delta_mean']:.3f} at Hit@5, "
        "with identical full and graph-disabled adaptive rankings on aggregate metrics.",
        "",
        "## Graph validation",
        "",
        f"All {summary['graph_path_checked']} reviewed supply-chain node paths were recovered within the accepted Top-5 path policy "
        f"(success={summary['graph_path_success_at_5']:.3f}). Structured nodes were excluded from text-chunk metrics.",
        "",
        "## Hit@5 by slice",
        "",
        "| Slice | Bottom-up | Top-down | Text RRF | Adaptive |",
        "|---|---:|---:|---:|---:|",
    ])
    for query_slice, values in formal["by_slice"].items():
        lines.append(
            f"| {query_slice} | {values['bottom_up']['hit_at_5']:.3f} | {values['top_down']['hit_at_5']:.3f} | "
            f"{values['text_rrf']['hit_at_5']:.3f} | {values['adaptive_full']['hit_at_5']:.3f} |"
        )
    lines.extend([
        "",
        "## Paper-safe conclusion",
        "",
        "The confirmatory held-out experiment supports a text-first architecture. Metadata-aware adaptive reranking improved ranking quality over naive text fusion without harming Hit@5, but it did not outperform Top-down Hit@5 and the paired Hit@5 improvement was not significant. The graph component should therefore be presented as an auditable structured-evidence and path-validation layer, not as the source of text-retrieval gains.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal", default=str(DEFAULT_FORMAL))
    parser.add_argument("--per-query", default=str(DEFAULT_PER_QUERY))
    parser.add_argument("--graph-validation", default=str(DEFAULT_GRAPH))
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite paper assets: {output}")

    formal = read_json(Path(args.formal))
    per_query = read_json(Path(args.per_query))
    graph = read_json(Path(args.graph_validation))
    lock = read_json(Path(args.lock))
    if formal["query_count"] != 30 or len(per_query) != 30:
        raise ValueError("formal held-out results must contain exactly 30 queries")
    if lock["selected_parameters"] != formal["selected_parameters"]:
        raise ValueError("formal parameters differ from the method lock")
    if graph["graph_path_validation"]["checked_count"] != 6:
        raise ValueError("expected six reviewed graph paths")
    if graph["graph_path_validation"]["success_at_5"] != 1.0:
        raise ValueError("not all reviewed graph paths were validated")
    if len({row["annotation_id"] for row in per_query}) != 30:
        raise ValueError("duplicate per-query IDs")
    for row in per_query:
        for variant in formal["variants"]:
            values = row["metrics"][variant]
            if not values["hit_at_1"] <= values["hit_at_3"] <= values["hit_at_5"]:
                raise ValueError(f"non-monotonic Hit@K for {row['annotation_id']} {variant}")
    text_improvements = [
        row["annotation_id"] for row in per_query
        if row["metrics"]["adaptive_full"]["hit_at_5"] > row["metrics"]["text_rrf"]["hit_at_5"]
    ]
    text_regressions = [
        row["annotation_id"] for row in per_query
        if row["metrics"]["adaptive_full"]["hit_at_5"] < row["metrics"]["text_rrf"]["hit_at_5"]
    ]
    if len(text_improvements) != 2 or text_regressions:
        raise ValueError(f"unexpected adaptive Hit@5 effects: improvements={text_improvements}, regressions={text_regressions}")
    if formal["aggregate"]["adaptive_full"] != formal["aggregate"]["adaptive_without_graph"]:
        raise ValueError("graph contribution is not zero despite the formal comparison")
    summary = {
        "query_count": 30,
        "adaptive_vs_text_rrf_hit_at_5_improvements": text_improvements,
        "adaptive_vs_text_rrf_hit_at_5_regressions": text_regressions,
        "graph_path_checked": graph["graph_path_validation"]["checked_count"],
        "graph_path_success_at_5": graph["graph_path_validation"]["success_at_5"],
        "method_lock_status": lock["lock_status"],
        "aggregate": formal["aggregate"],
        "paired_comparisons": formal["paired_comparisons"],
    }
    output.mkdir(parents=True)
    (output / "paper_ready_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "paper_ready_results.md").write_text(markdown_report(summary, formal), encoding="utf-8")
    (output / "table_overall.tex").write_text(overall_latex(formal), encoding="utf-8")
    (output / "table_by_slice.tex").write_text(slice_latex(formal), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "query_count": 30,
        "hit_at_5_improvements": text_improvements,
        "hit_at_5_regressions": text_regressions,
        "graph_path_validation": graph["graph_path_validation"],
    }, indent=2))


if __name__ == "__main__":
    main()
