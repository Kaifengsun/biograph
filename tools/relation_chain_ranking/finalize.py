from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from .common import chain_signature, read_json, sha256_file, sha256_json, write_json
from .config import FORBIDDEN_INFERENCE_KEYS


def _value(row: dict[str, Any], index: int) -> str:
    return str(list(row.values())[index] or "").strip()


def finalize_ledgers(
    registry: dict[str, Any],
    returned: dict[str, Any],
    consensus: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    questions = registry.get("questions", [])
    if len(questions) != 30:
        raise ValueError(f"expected 30 registry questions, got {len(questions)}")
    a_by_id = {row["review_id"]: row for row in returned.get("reviewer_a", [])}
    b_by_id = {row["review_id"]: row for row in returned.get("reviewer_b", [])}
    if len(a_by_id) != 30 or len(b_by_id) != 30 or set(a_by_id) != set(b_by_id):
        raise ValueError("returned independent reviews must contain matching 30-question ID sets")

    consensus_by_id: dict[str, dict[str, str]] = {}
    for row in consensus.get("rows", []):
        values = list(row.values())
        if len(values) < 15:
            raise ValueError("final consensus row has fewer than 15 columns")
        review_id = str(values[0]).strip()
        consensus_by_id[review_id] = {
            "status": _value(row, 11),
            "question": _value(row, 12),
            "answer": _value(row, 13),
            "note": _value(row, 14),
        }
    expected_disagreements = {
        review_id
        for review_id in a_by_id
        if any(
            str(a_by_id[review_id].get(field, "")).strip().casefold()
            != str(b_by_id[review_id].get(field, "")).strip().casefold()
            for field in ("status", "complete_chain_support", "provenance_adequacy")
        )
    }
    if set(consensus_by_id) != expected_disagreements or len(consensus_by_id) != 6:
        raise ValueError("consensus rows do not exactly match the six independent-review disagreements")

    private_rows = []
    public_rows = []
    inference_rows = []
    for source in questions:
        review_id = source["review_id"]
        original_question = str(source["question"]).strip()
        if review_id in consensus_by_id:
            decision = consensus_by_id[review_id]
            final_status = decision["status"]
            final_question = decision["question"]
            final_answer = decision["answer"]
            resolution = "joint_adjudication"
            adjudication_note = decision["note"]
        else:
            if str(a_by_id[review_id]["status"]).strip().casefold() != "confirmed":
                raise ValueError(f"non-adjudicated item is not jointly Confirmed: {review_id}")
            final_status = "Confirmed"
            final_question = original_question
            final_answer = str(source.get("draft_answer", "")).strip()
            resolution = "independent_agreement"
            adjudication_note = ""
        if final_status not in {"Confirmed", "Revise"}:
            raise ValueError(f"accepted final status required for {review_id}: {final_status}")
        if not final_question or not final_answer:
            raise ValueError(f"missing final question or answer: {review_id}")
        triples = [
            {"source": e["source"], "relation": e["relation"], "target": e["target"]}
            for e in source["edges"]
        ]
        signature = chain_signature(triples)
        nodes = sorted({part for edge in triples for part in (edge["source"], edge["target"])})
        base = {
            "review_id": review_id,
            "category": source["category"],
            "original_question": original_question,
            "final_question": final_question,
            "wording_changed": final_question != original_question,
            "final_status": final_status,
            "resolution": resolution,
            "final_answer": final_answer,
            "gold_edges": triples,
            "gold_nodes": nodes,
            "gold_signature": signature,
            "provenance_sources": list(source.get("provenance_sources", [])),
        }
        public_rows.append(base)
        private_rows.append(
            {
                **base,
                "reviewer_a": a_by_id[review_id],
                "reviewer_b": b_by_id[review_id],
                "adjudication_note": adjudication_note,
            }
        )
        inference_rows.append(
            {
                "review_id": review_id,
                "category": source["category"],
                "original_question": original_question,
                "final_question": final_question,
                "wording_changed": final_question != original_question,
            }
        )

    categories = Counter(row["category"] for row in public_rows)
    if set(categories.values()) != {10} or len(categories) != 3:
        raise ValueError(f"expected three 10-question categories, got {dict(categories)}")
    inference = {
        "schema_version": "1.0",
        "status": "sanitized_graph_chain_inference_input",
        "query_count": 30,
        "queries": inference_rows,
    }
    forbidden = []
    from .common import nested_forbidden_keys

    forbidden = nested_forbidden_keys(inference, FORBIDDEN_INFERENCE_KEYS)
    if forbidden:
        raise ValueError(f"forbidden inference keys: {forbidden}")
    public = {
        "schema_version": "1.0",
        "status": "sanitized_jointly_adjudicated_graph_chain_gold",
        "question_count": 30,
        "category_counts": dict(sorted(categories.items())),
        "questions": public_rows,
    }
    private = {
        "schema_version": "1.0",
        "status": "private_jointly_adjudicated_graph_chain_audit_ledger",
        "question_count": 30,
        "questions": private_rows,
    }
    return private, public, inference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--returned-reviews", type=Path, required=True)
    parser.add_argument("--consensus", type=Path, required=True)
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    registry = read_json(args.registry)
    returned = read_json(args.returned_reviews)
    consensus = read_json(args.consensus)
    private, public, inference = finalize_ledgers(registry, returned, consensus)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    private_path = args.output_dir / "private_audit_ledger.json"
    public_path = args.output_dir / "sanitized_gold_ledger.json"
    inference_path = args.output_dir / "inference_queries.json"
    write_json(private_path, private)
    write_json(public_path, public)
    write_json(inference_path, inference)
    manifest = {
        "schema_version": "1.0",
        "status": "graph_chain_gold_frozen",
        "inputs": {
            "registry": sha256_file(args.registry),
            "returned_reviews": sha256_file(args.returned_reviews),
            "consensus": sha256_file(args.consensus),
            "nodes": sha256_file(args.nodes),
            "edges": sha256_file(args.edges),
        },
        "outputs": {
            "private_audit_ledger": sha256_file(private_path),
            "sanitized_gold_ledger": sha256_file(public_path),
            "inference_queries": sha256_file(inference_path),
        },
        "public_gold_payload_sha256": sha256_json(public),
        "inference_payload_sha256": sha256_json(inference),
    }
    write_json(args.output_dir / "gold_integrity_manifest.json", manifest)
    print(f"frozen {public['question_count']} questions in {args.output_dir}")


if __name__ == "__main__":
    main()
