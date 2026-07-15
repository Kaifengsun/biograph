"""Prepare a method-blind 30-query confirmatory review pack without running retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4"
LOCK = ROOT / "outputs/selective_source_chunk_reranker_method_lock_2026-07-15/method_lock_manifest.json"
OUTPUT = ROOT / "data/eval/selective_reranker_confirmatory_review_candidates_2026-07-16.json"
REVIEW_COPY = ROOT / "outputs/selective_source_chunk_reranker_confirmatory_review_2026-07-16/review_payload.json"
SELECTION_SEED = "20260716"
SHUFFLE_SEED = "20260716-review"


HYDE_SELECTIONS = [
    # single_clause
    ("CONF-SC01", "single_clause", "ich_q5c_C0018_af504f75", "Why must the purity of a biotechnological/biological product be assessed by more than one method during stability testing?"),
    ("CONF-SC02", "single_clause", "ich_q3e_draft_C0117_fdbd66af", "According to the ICH Q3E draft guideline, what additional modifying factor is recommended to address uncertainty when a point of departure is derived from a surrogate compound using a read-across approach?"),
    ("CONF-SC03", "single_clause", "ich_q2r2_C0048_20fe52cc", "What is the minimum number of determinations required to assess repeatability at 100% of the test concentration according to the ICH Q2(R2) guideline?"),
    ("CONF-SC04", "single_clause", "ich_q6b_C0065_b0033d45", "When a biotechnological product is found to be heterogeneous with respect to terminal amino acids, what determination must be made using an appropriate analytical procedure?"),
    ("CONF-SC05", "single_clause", "ich_q1_draft_2025_C0220_9a5a2ff0", "In the ICH Q1 draft 2025 stability data evaluation, what statistical criterion determines whether a common slope/common intercept model is used for shelf life estimation?"),
    ("CONF-SC06", "single_clause", "ich_q5e_C0027_43df0c43", "What can be a consequence when comparability studies on quality attributes indicate that physicochemical and biological tests alone are inadequate?"),
    ("CONF-SC07", "single_clause", "ich_q5a_r2_C0065_7a5dc063", "Which types of virus titration assay methods are identified as amenable to statistical evaluation?"),
    ("CONF-SC08", "single_clause", "ich_q13_C0092_57e72c99", "What details must be provided regarding drug substance purity in the design of an integrated process that uses different purification methods or a mix of batch and continuous unit operations?"),
    ("CONF-SC09", "single_clause", "ich_q11_C0041_221ad793", "According to ICH Q11, what format options are acceptable for presenting the summary of the overall drug substance control strategy?"),
    ("CONF-SC10", "single_clause", "ich_q3c_r9_C0089_20887f34", "What mode of action for renal tumors in male rats exposed to TBA is described as sex- and species-specific and not relevant to humans?"),
    # table
    ("CONF-TB01", "table", "ich_q1d_C0021_ce79f9ba", "In a matrixing design that reduces testing on both time points and factors, are certain combinations of batch, strength, and container size omitted from testing?"),
    ("CONF-TB02", "table", "ich_q5a_r2_C0076_7c829bfe", "What concentration and minimum contact time of Triton X-100 are required to effectively inactivate XMLV in clarified HCCF according to the current process understanding?"),
    ("CONF-TB03", "table", "ich_q3a_r2_C0022_0c4384ec", "What is the reporting threshold for impurities in a new drug substance when the maximum daily dose is 2 g/day or less?"),
    ("CONF-TB04", "table", "ich_q3d_r2_C0278_792c4264", "When a calculated cutaneous concentration based on the PDE conflicts with the CTCL for sensitizing elements like nickel or cobalt, which limit must be applied?"),
    ("CONF-TB05", "table", "ich_q13_C0102_872a2af0", "What does the example in Table 4 state about tests that are common to both drug substance and drug product specifications?"),
    ("CONF-TB06", "table", "ich_q1_draft_2025_C0065_69272ccd", "What water loss threshold is considered a significant change for a product in a semi-permeable container after 3 months at 40°C/≤25% RH?"),
    ("CONF-TB07", "table", "ich_q14_C0108_01d0e167", "What performance characteristics and criteria are described in the ATP according to the excerpt?"),
    ("CONF-TB08", "table", "ich_q3b_r2_C0010_32801c96", "At what total daily intake of a degradation product does the identification threshold of 2 mg become exceeded?"),
    # document_structure
    ("CONF-DS01", "document_structure", "ich_q11_C0048_b2ceca30", "In which section of the application should the design space be described as an element of the proposed manufacturing process and process controls?"),
    ("CONF-DS02", "document_structure", "ich_q12_C0040_225be9cd", "Where in the Common Technical Document can the product lifecycle management document be located according to the ICH Q12 guideline?"),
    ("CONF-DS03", "document_structure", "fda_cgmp_guidance_C0032_b9409708", "Where can the specifics of the correlation between quality system elements and CGMP requirements be found in the FDA guidance?"),
    ("CONF-DS04", "document_structure", "ich_q3c_r9_C0013_c56e5ca0", "Where are the toxicity data summaries that support the residual solvent limits published?"),
    ("CONF-DS05", "document_structure", "ich_q4b_C0024_7d7b22fb", "Which document includes the Q4B Outcome after a pharmacopoeial text receives a favourable evaluation?"),
    ("CONF-DS06", "document_structure", "ich_q1_draft_2025_C0046_0cd5f1fa", "Which sections of a stability protocol should be informed by a science- and risk-based approach according to the excerpt?"),
]


CROSS_SELECTIONS = [
    ("CONF-CD01", "MS001", "How do ICH Q9 risk management principles integrate with ICH Q10 pharmaceutical quality systems to control manufacturing process risks?", ["ich_q9_C0007_6a76fd84", "ich_q10_C0004_a8fb88f4"]),
    ("CONF-CD02", "MS002", "How should EMA GMP Annex 11 computerized system validation requirements be implemented within the ICH Q10 lifecycle management framework?", ["ema_gmp_annex_11_C0008_fc827afb", "ich_q10_C0005_f84321ff"]),
    ("CONF-CD03", "MS004", "How do ICH Q10 CAPA (Corrective and Preventive Action) requirements connect to FDA cGMP deviation investigation procedures?", ["ich_q10_C0014_acfb72b4", "fda_cgmp_guidance_C0030_be4bf056", "fda_cgmp_guidance_C0036_c0ee04d7"]),
    ("CONF-CD04", "MS008", "How do ICH Q10 knowledge management requirements support the ongoing process verification described in FDA Process Validation Guidance?", ["ich_q10_C0032_60da690f", "fda_cgmp_guidance_C0025_1bb348a4"]),
    ("CONF-CD05", "MS010", "How do EMA GMP Annex 11 data integrity requirements align with the ICH Q9 risk-based approach to determine computerized system criticality?", ["ema_gmp_annex_11_C0005_1fd76a4b", "ema_gmp_annex_11_C0009_a068f09a", "ich_q9_C0012_cef84513"]),
    ("CONF-CD06", "MS014", "What ICH Q10 and ICH Q9 requirements govern change control procedures when a pharmaceutical manufacturer modifies a critical manufacturing step following a supply disruption?", ["ich_q10_C0015_270983de", "ich_q10_C0016_192f9b01", "ich_q9_C0092_ca9c63da"]),
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def hashed_order(label: str, values: list[str]) -> list[str]:
    return sorted(values, key=lambda value: hashlib.sha256(f"{label}:{value}".encode()).hexdigest())


def main() -> None:
    if OUTPUT.exists() or REVIEW_COPY.exists():
        raise RuntimeError("refusing to overwrite confirmatory review artifacts")
    corpus_rows: list[dict[str, Any]] = []
    source_file_by_chunk: dict[str, str] = {}
    for path in sorted(CORPUS.glob("*_enriched.json")):
        rows = read_json(path)
        corpus_rows.extend(rows)
        source_file_by_chunk.update({str(row["chunk_id"]): path.name for row in rows})
    records = {str(row["chunk_id"]): row for row in corpus_rows}
    if len(records) != 2478:
        raise ValueError("unexpected frozen corpus size")

    used_queries: list[dict[str, Any]] = []
    for path in (
        ROOT / "data/eval/three_path_evaluation_frozen_2026-07-15.json",
        ROOT / "data/eval/bm25_enrichment_heldout_frozen_run_ready_2026-07-15.json",
    ):
        used_queries.extend(read_json(path)["queries"])
    used_normalized = {normalized(row["query"]) for row in used_queries}
    used_ids = {str(row["annotation_id"]) for row in used_queries}

    questions: list[dict[str, Any]] = []
    for review_id, query_slice, chunk_id, query in HYDE_SELECTIONS:
        if chunk_id not in records or query not in (records[chunk_id].get("hyde_questions") or []):
            raise ValueError(f"HyDE source mismatch: {review_id}")
        questions.append({
            "annotation_id": review_id, "query_slice": query_slice, "query": query,
            "source_question_id": f"hyde:{chunk_id}", "seed_chunk_ids": [chunk_id],
            "question_provenance": "preexisting_deepseek_v4_pro_hyde_question",
        })
    for review_id, source_id, query, seed_chunks in CROSS_SELECTIONS:
        if source_id in used_ids or any(chunk_id not in records for chunk_id in seed_chunks):
            raise ValueError(f"cross-document source mismatch: {review_id}")
        questions.append({
            "annotation_id": review_id, "query_slice": "cross_document", "query": query,
            "source_question_id": source_id, "seed_chunk_ids": seed_chunks,
            "question_provenance": "preexisting_entity_anchor_question_with_section_notes",
        })

    counts = {query_slice: sum(row["query_slice"] == query_slice for row in questions) for query_slice in ("single_clause", "table", "document_structure", "cross_document")}
    if counts != {"single_clause": 10, "table": 8, "document_structure": 6, "cross_document": 6}:
        raise ValueError(counts)
    if len({normalized(row["query"]) for row in questions}) != 30:
        raise ValueError("duplicate confirmatory questions")
    overlap = sorted({normalized(row["query"]) for row in questions} & used_normalized)
    if overlap:
        raise ValueError(f"confirmatory question overlap: {overlap}")

    all_ids = sorted(records)
    for question in questions:
        seeds = question["seed_chunk_ids"]
        pool: set[str] = set(seeds)
        for seed in seeds:
            row = records[seed]
            pool.update(chunk_id for chunk_id in (row.get("prev_chunk_id"), row.get("next_chunk_id")) if chunk_id in records)
        sibling_candidates = [
            chunk_id for chunk_id, row in records.items()
            if chunk_id not in pool
            and row.get("doc_id") in {records[seed].get("doc_id") for seed in seeds}
            and any(
                row.get("level") == records[seed].get("level")
                and row.get("parents_context") == records[seed].get("parents_context")
                for seed in seeds
            )
        ]
        pool.update(hashed_order(f"{SELECTION_SEED}:{question['annotation_id']}:sibling", sibling_candidates)[:8])
        source_docs = {records[seed].get("doc_id") for seed in seeds}
        distractors = [chunk_id for chunk_id in all_ids if chunk_id not in pool and records[chunk_id].get("doc_id") not in source_docs]
        pool.update(hashed_order(f"{SELECTION_SEED}:{question['annotation_id']}:distractor", distractors)[:4])
        shuffled = hashed_order(f"{SHUFFLE_SEED}:{question['annotation_id']}", sorted(pool))
        passages = []
        for index, chunk_id in enumerate(shuffled, 1):
            row = records[chunk_id]
            passages.append({
                "passage_id": f"P{index:02d}", "chunk_id": chunk_id,
                "doc_id": row.get("doc_id", ""), "heading": row.get("heading", ""),
                "original_source_passage": row.get("content", ""),
                "frozen_source_file": source_file_by_chunk[chunk_id],
                "pool_role": "seed" if chunk_id in seeds else "context_or_distractor",
            })
        question.update({
            "review_status": "Pending", "gold_passage_ids": [], "gold_evidence_chunk_ids": [],
            "review_note": "", "passages": passages,
        })

    query_payload = [
        {"annotation_id": row["annotation_id"], "query_slice": row["query_slice"], "query": row["query"]}
        for row in questions
    ]
    pack = {
        "schema_version": "1.0", "status": "pending_blinded_human_review",
        "formal_metrics_ready": False, "retrieval_execution_prohibited": True,
        "confirmatory_for_source_chunk_reranker": True,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "selection_seed": SELECTION_SEED, "passage_shuffle_seed": SHUFFLE_SEED,
        "question_count": 30, "slice_counts": counts,
        "query_content_sha256": hashlib.sha256(json.dumps(query_payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "method_lock": {"path": str(LOCK.relative_to(ROOT)), "sha256": sha256_file(LOCK)},
        "overlap_checks": {"existing_90_normalized_question_overlap": 0, "existing_90_annotation_id_overlap": 0},
        "review_blinding": {
            "method_names_hidden": True, "retrieval_scores_hidden": True, "retrieval_ranks_hidden": True,
            "passage_order": "sha256_deterministic_shuffle",
        },
        "questions": questions,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_COPY.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(pack, ensure_ascii=False, indent=2)
    OUTPUT.write_text(content, encoding="utf-8")
    REVIEW_COPY.write_text(content, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "review_copy": str(REVIEW_COPY), "question_count": 30, "slice_counts": counts, "query_content_sha256": pack["query_content_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
