"""Validate manuscript citations, evidence labels, and traceable result values."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parent
RESULTS = ROOT / "outputs/modern_reranker_58_2026-07-16/qwen3_direct_posthoc_evaluation.json"
GRAPH_RESULTS = ROOT / (
    "outputs/relation_chain_ranking_30_2026-07-18/"
    "evaluation_v4_audit_qualified_v2.json"
)
REPORT = PAPER / "validation/manuscript_validation.json"


def load_tex() -> dict[str, str]:
    paths = [PAPER / "main.tex", PAPER / "supplementary.tex"]
    paths.extend(sorted((PAPER / "sections").glob("*.tex")))
    paths.extend(sorted((PAPER / "tables").glob("*.tex")))
    return {path.relative_to(PAPER).as_posix(): path.read_text(encoding="utf-8") for path in paths}


def main() -> None:
    tex_files = load_tex()
    all_tex = "\n".join(tex_files.values())
    bib_text = (PAPER / "references.bib").read_text(encoding="utf-8")
    bib_keys = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib_text))
    citation_keys: set[str] = set()
    for group in re.findall(r"\\cite\w*\{([^}]+)\}", all_tex):
        citation_keys.update(key.strip() for key in group.split(",") if key.strip())

    with (PAPER / "citation_audit.csv").open(encoding="utf-8", newline="") as handle:
        audit_rows = list(csv.DictReader(handle))
    audit_keys = {row["citation_key"] for row in audit_rows}
    audit_verified = all(
        row["metadata_status"] == "verified" and row["claim_support_status"] == "verified"
        for row in audit_rows
    )

    doi_values = [value.lower() for value in re.findall(r"doi\s*=\s*\{([^}]+)\}", bib_text, re.I)]
    duplicate_dois = sorted({doi for doi in doi_values if doi_values.count(doi) > 1})
    figure_pngs = [
        "figures/dual_path_framework.png",
        "figures/retrieval_findings_summary.png",
    ]
    figure_svgs = [
        "figures/dual_path_framework.svg",
        "figures/retrieval_findings_summary.svg",
    ]
    checks: dict[str, bool] = {
        "all_citations_have_bib_entries": citation_keys <= bib_keys,
        "all_bib_entries_are_audited": bib_keys <= audit_keys,
        "all_audit_entries_are_in_bib": audit_keys <= bib_keys,
        "all_audit_rows_verified": audit_verified,
        "no_duplicate_dois": not duplicate_dois,
        # Provider keys may contain letters, digits, underscores, and dots after
        # the prefix. Excluding hyphens avoids flagging ordinary URL slugs such
        # as "risk-management-plans".
        "no_secret_like_api_keys": re.search(r"sk-[A-Za-z0-9_.]{20,}", all_tex + bib_text) is None,
        "qwen3_called_supplementary": "supplementary" in all_tex.lower(),
        "qwen3_called_post_hoc": "post hoc" in all_tex.lower(),
        "no_qwen3_superiority_claim": re.search(
            r"qwen3[^.]{0,100}\b(significantly superior|confirmed superiority|outperforms bm25)\b",
            all_tex,
            re.I,
        ) is None,
        "required_figures_present": all((PAPER / path).is_file() for path in figure_pngs),
        "required_figure_sources_present": all((PAPER / path).is_file() for path in figure_svgs),
        "required_figures_referenced": all(path in all_tex for path in figure_pngs),
    }

    result_checks: dict[str, bool] = {}
    if RESULTS.exists():
        payload = json.loads(RESULTS.read_text(encoding="utf-8"))
        bm25 = payload["aggregate"]["BM25_context_matched"]
        qwen = payload["aggregate"]["Qwen3_posthoc_reranker"]
        paired = payload["paired_bootstrap_qwen3_minus_bm25"]
        expected = {
            "bm25_hit5": (bm25["hit_at_5"], "0.948"),
            "bm25_mrr": (bm25["mrr_at_50"], "0.820"),
            "bm25_ndcg5": (bm25["ndcg_at_5"], "0.800"),
            "qwen_hit5": (qwen["hit_at_5"], "0.983"),
            "qwen_mrr": (qwen["mrr_at_50"], "0.832"),
            "qwen_ndcg5": (qwen["ndcg_at_5"], "0.817"),
            "qwen_hit5_delta": (paired["hit_at_5"]["delta_mean"], "0.034"),
            "qwen_mrr_delta": (paired["mrr_at_50"]["delta_mean"], "0.012"),
            "qwen_ndcg_delta": (paired["ndcg_at_5"]["delta_mean"], "0.017"),
        }
        for name, (actual, rendered) in expected.items():
            result_checks[name] = f"{actual:.3f}" == rendered and rendered in all_tex
    else:
        result_checks["local_results_available"] = False

    if GRAPH_RESULTS.exists():
        payload = json.loads(GRAPH_RESULTS.read_text(encoding="utf-8"))
        strict = payload["strict_metrics"]
        r1 = strict["aggregate"]["r1"]
        m0_delta = strict["paired_bootstrap"]["r1_minus_m0"]["hit_at_5"]
        direction_delta = strict["paired_bootstrap"]["r1_minus_direction_off"]["hit_at_5"]
        graph_expected = {
            "graph_strict_n": (strict["query_count"], "28"),
            "graph_r1_hit1": (r1["hit_at_1"], "0.571"),
            "graph_r1_hit5": (r1["hit_at_5"], "0.786"),
            "graph_r1_mrr": (r1["mrr"], "0.663"),
            "graph_r1_m0_hit5_delta": (m0_delta["delta"], "0.643"),
            "graph_r1_direction_hit5_delta": (direction_delta["delta"], "0.036"),
        }
        for name, (actual, rendered) in graph_expected.items():
            if isinstance(actual, int):
                result_checks[name] = str(actual) == rendered and rendered in all_tex
            else:
                result_checks[name] = f"{actual:.3f}" == rendered and rendered in all_tex
    else:
        result_checks["local_graph_results_available"] = False

    checks["all_result_values_traceable"] = all(result_checks.values())
    report = {
        "schema_version": "1.0",
        "checks": checks,
        "result_checks": result_checks,
        "missing_bib_keys": sorted(citation_keys - bib_keys),
        "unaudited_bib_keys": sorted(bib_keys - audit_keys),
        "orphan_audit_keys": sorted(audit_keys - bib_keys),
        "duplicate_dois": duplicate_dois,
        "cited_key_count": len(citation_keys),
        "bibliography_entry_count": len(bib_keys),
        "passed": all(checks.values()),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
