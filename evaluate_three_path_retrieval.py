"""Evaluate predeclared three-path variants only on a frozen human-reviewed snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from three_path_evaluation import VARIANTS, evaluate_retrieval, sha256_file, validate_frozen_pack


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Three-Path Retrieval Evaluation",
        "",
        f"Frozen reviewed queries: {report['query_count']}",
        "",
        "| Variant | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in VARIANTS:
        values = report["aggregate"][variant]
        label = {"bottom_up": "Bottom-up", "top_down": "Top-down", "graph_path": "Graph path", "three_path_rrf": "Three-path RRF"}[variant]
        lines.append(f"| {label} | {values['hit_at_1']:.3f} | {values['hit_at_3']:.3f} | {values['hit_at_5']:.3f} | {values['mrr']:.3f} | {values['ndcg_at_5']:.3f} |")
    lines.extend(["", f"Fusion policy: {report['fusion']}"])
    lines.append(f"Graph-path validation policy: {report['graph_path_validation_policy']}")
    checked = report["graph_path_validation"]
    if checked["checked_count"]:
        lines.append(f"Graph-path validation: {checked['success_at_5']:.3f} across {checked['checked_count']} reviewed paths.")
    else:
        lines.append("Graph-path validation: no reviewed graph paths were available; report qualitative cases only.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate frozen three-path retrieval outputs")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--retrieval", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pack_path = Path(args.pack)
    retrieval_path = Path(args.retrieval)
    output = Path(args.output)
    markdown_output = output.with_suffix(".md")
    if output.exists() or markdown_output.exists():
        raise RuntimeError(f"refusing to overwrite existing evaluation output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = validate_frozen_pack(read_json(pack_path))
    report = evaluate_retrieval(rows, read_json(retrieval_path))
    report["evaluation"] = {
        "formal_metrics": True,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pack": str(pack_path),
        "pack_sha256": sha256_file(pack_path),
        "retrieval": str(retrieval_path),
        "retrieval_sha256": sha256_file(retrieval_path),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"formal_metrics": True, "query_count": report["query_count"], "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
