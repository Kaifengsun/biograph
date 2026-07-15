"""Prepare a review-only table-retrieval evaluation candidate set.

This script links existing gap-fill questions to the frozen DeepSeek table
artifacts using transparent lexical evidence. It deliberately does not mark
any mapping as formal ground truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STAGING = ROOT / "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4"
GAP_FILL = ROOT / "data/eval/query_candidates_v2_gap_fill_2026-06-10.json"
OUTPUT = ROOT / "data/eval/table_query_candidates_deepseek_v4_2026-07-10.json"


DOC_TO_STEM = {
    "ICH Q1A": "ich_q1a",
    "ICH Q1B": "ich_q1b",
    "ICH Q2(R2)": "ich_q2r2",
    "ICH M7(R2)": "ich_m7_r2",
    "ICH Q3A(R2)": "ich_q3a_r2",
    "ICH Q3B(R2)": "ich_q3b_r2",
    "ICH Q3C(R9)": "ich_q3c_r9",
    "ICH Q3D(R2)": "ich_q3d_r2",
    "ICH Q6B": "ich_q6b",
    "WHO Stability Q1F": "who_stability_q1f",
    "WHO EML 2023": "who_eml_2023",
}


def _words(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2
    }


def _score_table(table: dict[str, Any], signals: list[str]) -> float:
    summary = " ".join(str(table.get(k, "")) for k in ("table_summary", "table"))
    summary_lower = summary.lower()
    summary_words = _words(summary)
    score = 0.0
    for signal in signals:
        phrase = signal.lower().strip()
        if not phrase:
            continue
        if phrase in summary_lower:
            score += 3.0
        score += 0.35 * len(_words(phrase) & summary_words)
    if table.get("table_summary"):
        score += 0.1
    return round(score, 4)


def main() -> None:
    gap_fill = json.loads(GAP_FILL.read_text(encoding="utf-8"))
    candidates = [
        item
        for item in gap_fill["candidates"]
        if item.get("candidate_id", "").startswith("gapfill:TB")
    ]

    output_queries: list[dict[str, Any]] = []
    missing_docs: set[str] = set()
    for item in candidates:
        docs = item.get("candidate_relevant_docs", [])
        evidence: list[dict[str, Any]] = []
        signals = item.get("expected_evidence_signals", [])
        for doc in docs:
            stem = DOC_TO_STEM.get(doc)
            if not stem:
                missing_docs.add(doc)
                continue
            table_path = STAGING / f"{stem}_tables.json"
            if not table_path.exists():
                missing_docs.add(doc)
                continue
            tables = json.loads(table_path.read_text(encoding="utf-8"))
            ranked = sorted(
                ((
                    _score_table(table, signals),
                    table,
                ) for table in tables),
                key=lambda pair: (-pair[0], pair[1].get("chunk_id", "")),
            )
            for score, table in ranked[:5]:
                evidence.append(
                    {
                        "doc_id": stem,
                        "source_doc": doc,
                        "table_chunk_id": table.get("chunk_id"),
                        "lexical_candidate_score": score,
                        "table_summary": table.get("table_summary", ""),
                        "source_table_preview": str(table.get("table", ""))[:1200],
                    }
                )

        evidence.sort(
            key=lambda row: (-row["lexical_candidate_score"], row["table_chunk_id"] or "")
        )
        viable_ids = [
            row["table_chunk_id"]
            for row in evidence
            if row["table_chunk_id"] and row["lexical_candidate_score"] >= 1.0
        ]
        output_queries.append(
            {
                "candidate_id": item["candidate_id"],
                "query": item["query"],
                "category": item.get("proposed_category"),
                "difficulty": item.get("difficulty"),
                "relevant_docs": docs,
                "expected_evidence_signals": signals,
                "target_capability": item.get("target_capability", []),
                "candidate_table_chunk_ids": viable_ids,
                "table_evidence_candidates": evidence,
                "status": (
                    "table_candidate_requires_manual_validation"
                    if viable_ids
                    else "no_viable_table_evidence_in_frozen_corpus"
                ),
                "eligible_for_formal_evaluation": False,
                "provenance": {
                    "query_source": "data/eval/query_candidates_v2_gap_fill_2026-06-10.json",
                    "table_source_root": "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4",
                    "candidate_selection": "lexical ranking over existing table text and source-grounded table summaries",
                },
            }
        )

    result = {
        "generated_at": "2026-07-10",
        "status": "review_only_candidate_set",
        "formal_evaluation_eligible": False,
        "query_count": len(output_queries),
        "scope": "dedicated table-retrieval questions",
        "limitations": [
            "Table chunk mappings are lexical candidates and require source/query review.",
            "No query is promoted to ground truth by this script.",
            "The set measures table retrieval support, not answer correctness by itself.",
        ],
        "missing_source_documents": sorted(missing_docs),
        "candidates": output_queries,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "query_count": len(output_queries),
        "queries_with_candidates": sum(bool(q["candidate_table_chunk_ids"]) for q in output_queries),
        "missing_source_documents": sorted(missing_docs),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
