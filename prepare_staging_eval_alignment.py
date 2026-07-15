"""Map legacy evaluation evidence IDs to candidate IDs in a frozen corpus.

The generated file is deliberately marked as needing human review. It must not
be treated as formal retrieval ground truth until the candidate evidence is
checked against the query and source text.
"""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


DEFAULT_QUERIES = Path("data/eval_queries.json")
DEFAULT_LEGACY = Path("data/chunks")
DEFAULT_FROZEN = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
DEFAULT_OUTPUT = Path("data/eval/eval_queries_deepseek_v4_candidate_2026-07-10.json")
DEFAULT_REPORT = Path("data/eval/deepseek_v4_evidence_alignment_report_2026-07-10.json")
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.lower()))


def token_overlap(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def normalized_text(value: str) -> str:
    return " ".join(TOKEN_RE.findall(value.lower()))


def content_similarity(left: str, right: str) -> float:
    left_n, right_n = normalized_text(left), normalized_text(right)
    if not left_n or not right_n:
        return 0.0
    if left_n in right_n or right_n in left_n:
        return 1.0
    return max(
        token_overlap(left_n, right_n),
        SequenceMatcher(None, left_n[:3000], right_n[:3000]).ratio(),
    )


def score_candidate(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, float]:
    heading = content_similarity(old.get("heading", ""), new.get("heading", ""))
    content = content_similarity(old.get("content", ""), new.get("content", ""))
    return {
        "heading_score": round(heading, 4),
        "content_score": round(content, 4),
        "score": round(0.4 * heading + 0.6 * content, 4),
    }


def load_records(directory: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*_enriched.json")):
        rows = read_json(path)
        if isinstance(rows, list):
            records.extend(rows)
    if not records:
        raise RuntimeError(f"no enriched records found in {directory}")
    return records


def rank_candidates(old: Dict[str, Any], candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = []
    for new in candidates:
        scores = score_candidate(old, new)
        ranked.append(
            {
                "new_chunk_id": new.get("chunk_id", ""),
                "new_heading": new.get("heading", ""),
                "new_content_preview": new.get("content", "")[:500],
                **scores,
            }
        )
    return sorted(ranked, key=lambda row: row["score"], reverse=True)[:3]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare candidate evidence alignment")
    parser.add_argument("--queries", default=str(DEFAULT_QUERIES))
    parser.add_argument("--legacy", default=str(DEFAULT_LEGACY))
    parser.add_argument("--frozen", default=str(DEFAULT_FROZEN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    output, report_path = Path(args.output), Path(args.report)
    if output.exists() or report_path.exists():
        raise RuntimeError("refusing to overwrite existing candidate alignment artifacts")

    legacy = load_records(Path(args.legacy))
    frozen = load_records(Path(args.frozen))
    legacy_by_id = {normalize_id(row.get("chunk_id", "")): row for row in legacy}
    frozen_by_doc: Dict[str, List[Dict[str, Any]]] = {}
    for row in frozen:
        frozen_by_doc.setdefault(row.get("doc_id", ""), []).append(row)

    queries = read_json(Path(args.queries))
    aligned = []
    mappings = []
    unresolved = []
    for query in queries:
        if query.get("status") != "annotated" or not query.get("relevant_chunk_ids"):
            continue
        candidates = []
        for legacy_id in query["relevant_chunk_ids"]:
            old = legacy_by_id.get(normalize_id(legacy_id))
            if old is None:
                unresolved.append({"query_id": query.get("query_id"), "legacy_chunk_id": legacy_id})
                continue
            doc_candidates = frozen_by_doc.get(old.get("doc_id", ""), [])
            ranked = rank_candidates(old, doc_candidates)
            if not ranked:
                unresolved.append({"query_id": query.get("query_id"), "legacy_chunk_id": legacy_id})
                continue
            best = ranked[0]
            mapping = {
                "legacy_chunk_id": legacy_id,
                "legacy_doc_id": old.get("doc_id", ""),
                "legacy_heading": old.get("heading", ""),
                "legacy_content_preview": old.get("content", "")[:500],
                "candidate_new_chunk_id": best["new_chunk_id"],
                "candidate_new_heading": best["new_heading"],
                "score": best["score"],
                "heading_score": best["heading_score"],
                "content_score": best["content_score"],
                "alternatives": ranked[1:],
                "needs_human_review": True,
            }
            candidates.append(mapping)
            mappings.append({"query_id": query.get("query_id"), **mapping})

        copied = dict(query)
        copied["legacy_relevant_chunk_ids"] = list(query.get("relevant_chunk_ids", []))
        copied["relevant_chunk_ids"] = []
        copied["candidate_relevant_chunk_ids"] = [
            item["candidate_new_chunk_id"] for item in candidates
        ]
        copied["candidate_evidence_mappings"] = candidates
        copied["status"] = "candidate_mapped_needs_review"
        copied["eligible_for_formal_evaluation"] = False
        aligned.append(copied)

    score_values = [item["score"] for item in mappings]
    report = {
        "source_queries": str(args.queries),
        "legacy_corpus": str(args.legacy),
        "frozen_corpus": str(args.frozen),
        "annotated_queries_seen": len(aligned),
        "legacy_labels_mapped": len(mappings),
        "unresolved_labels": unresolved,
        "score_summary": {
            "min": round(min(score_values), 4) if score_values else None,
            "mean": round(sum(score_values) / len(score_values), 4) if score_values else None,
            "below_0_5": sum(score < 0.5 for score in score_values),
            "below_0_7": sum(score < 0.7 for score in score_values),
        },
        "formal_evaluation_ready": False,
        "review_requirement": (
            "Verify each candidate against the query and frozen source text before "
            "moving it into a formal gold-label file."
        ),
    }
    write_json(output, aligned)
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
