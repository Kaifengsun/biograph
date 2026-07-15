"""Convert legacy retrieval query files into a non-destructive candidate pool."""

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path


DEFAULT_OUTPUT = Path("data/eval/query_candidates_v1.json")
INPUTS = [
    ("base", Path("data/eval_queries.json")),
    ("entity_anchor", Path("data/eval_queries_entity_anchor.json")),
]

CATEGORY_MAP = {
    "single_gmp": "single_clause",
    "single_regulatory": "single_clause",
    "cross_document": "cross_document",
    "multi_hop_cross_doc": "cross_document",
    "multi_hop_chain": "supply_chain_scenario",
    "supply_chain": "supply_chain_scenario",
    "supply_chain_risk": "supply_chain_scenario",
}


def paired_query_id(source_kind: str, source_query_id: str) -> str:
    if source_kind != "entity_anchor" or not source_query_id.startswith("EA"):
        return source_query_id
    return f"Q{source_query_id[2:]}"


def ground_truth_provenance(original_status: str) -> str:
    if original_status == "annotated":
        return "legacy_annotation_candidate_requires_revalidation"
    if original_status == "keyword_search":
        return "keyword_search_debug_only"
    return "incomplete_legacy_candidate"


def prepare_candidates(output_path: Path) -> dict:
    if output_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing candidate pool: {output_path}")

    candidates = []
    for source_kind, source_path in INPUTS:
        rows = json.loads(source_path.read_text(encoding="utf-8"))
        for row in rows:
            source_query_id = row["query_id"]
            original_category = row.get("category", "unclassified")
            original_status = row.get("status", "missing")
            candidates.append(
                {
                    "candidate_id": f"{source_kind}:{source_query_id}",
                    "source_file": str(source_path),
                    "source_query_id": source_query_id,
                    "paired_query_id": paired_query_id(source_kind, source_query_id),
                    "query_variant": source_kind,
                    "query": row["query"],
                    "proposed_category": CATEGORY_MAP.get(
                        original_category,
                        "manual_category_review",
                    ),
                    "original_category": original_category,
                    "difficulty": row.get("difficulty"),
                    "candidate_relevant_docs": row.get("relevant_docs", []),
                    "candidate_relevant_chunk_ids": row.get("relevant_chunk_ids", []),
                    "legacy_notes": row.get("notes", ""),
                    "original_status": original_status,
                    "ground_truth_provenance": ground_truth_provenance(original_status),
                    "annotation_status": "candidate_requires_manual_validation",
                    "eligible_for_formal_evaluation": False,
                }
            )

    output = {
        "generated_at": date.today().isoformat(),
        "status": "candidate_pool_only",
        "formal_evaluation_eligible": False,
        "annotation_guidelines": "data/eval/annotation_guidelines.md",
        "source_files": [str(path) for _, path in INPUTS],
        "summary": {
            "candidates": len(candidates),
            "query_variants": dict(Counter(c["query_variant"] for c in candidates)),
            "proposed_categories": dict(
                Counter(c["proposed_category"] for c in candidates)
            ),
            "ground_truth_provenance": dict(
                Counter(c["ground_truth_provenance"] for c in candidates)
            ),
        },
        "candidates": candidates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = prepare_candidates(args.output)
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
