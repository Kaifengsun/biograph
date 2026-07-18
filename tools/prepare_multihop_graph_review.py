"""Build a deterministic 30-question graph-path validity registry."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = ROOT / "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def edge_key(source: str, relation: str, target: str) -> tuple[str, str, str]:
    return source, relation, target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite: {args.output}")

    nodes_path = args.graph / "nodes.jsonl"
    edges_path = args.graph / "edges.jsonl"
    nodes = read_jsonl(nodes_path)
    edges = read_jsonl(edges_path)
    by_id = {row["id"]: row for row in nodes}
    by_edge = {edge_key(row["source"], row["relation"], row["target"]): row for row in edges}
    outgoing: dict[tuple[str, str], list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[(edge["source"], edge["relation"])].append(edge["target"])

    questions: list[dict[str, Any]] = []

    shortage_ids = (
        "fda_shortage:00502f8787fd082c4ae1",
        "fda_shortage:014c74357a4f8389b956",
        "fda_shortage:054d7d4aeb3f4043b7be",
        "fda_shortage:0775bbd92c0244cbeda8",
        "fda_shortage:0aa0dcfadc10d282e73c",
        "fda_shortage:0afdb112d2a3993fccc5",
        "fda_shortage:0b3ac07ad35fc778b3ad",
        "fda_shortage:0b65ad037ab2b4408c3d",
        "fda_shortage:1320bb7c6fedabe74c3a",
        "fda_shortage:13587d0a8d41cdb8b7a9",
    )
    for index, event_id in enumerate(shortage_ids, 1):
        event = by_id[event_id]
        ndc_ids = outgoing[(event_id, "AFFECTS_NDC_PRODUCT")]
        company_ids = outgoing[(event_id, "REPORTED_BY")]
        ingredient_ids = sorted({
            ingredient
            for ndc_id in ndc_ids
            for ingredient in outgoing[(ndc_id, "HAS_ACTIVE_INGREDIENT")]
        })
        if len(ndc_ids) != 1 or len(company_ids) != 1 or not ingredient_ids:
            raise ValueError(f"shortage template requires one NDC, one company, and ingredients: {event_id}")
        ndc_id, company_id = ndc_ids[0], company_ids[0]
        path_edges = [
            (event_id, "REPORTED_BY", company_id),
            (event_id, "AFFECTS_NDC_PRODUCT", ndc_id),
            *[(ndc_id, "HAS_ACTIVE_INGREDIENT", ingredient_id) for ingredient_id in ingredient_ids],
        ]
        props = event["properties"]
        questions.append({
            "review_id": f"MH-SH{index:02d}",
            "category": "shortage_chain",
            "question": (
                f"For the current FDA shortage record for {event['name']} with package NDC "
                f"{props['package_ndc']}, which company reported it, what availability and "
                "shortage reason were recorded, and which active ingredient(s) are linked to the NDC product?"
            ),
            "draft_answer": (
                f"{by_id[company_id]['name']}; availability: {props['availability']}; reason: "
                f"{props['shortage_reason']}; active ingredient(s): "
                f"{', '.join(by_id[row]['name'] for row in ingredient_ids)}."
            ),
            "node_ids": [event_id, company_id, ndc_id, *ingredient_ids],
            "edges": [by_edge[row] for row in path_edges],
        })

    supply_specs = (
        ("entity:DRUG_acetaminophen", "entity:API_acetaminophen"),
        ("entity:DRUG_acyclovir", "entity:API_acyclovir"),
        ("entity:DRUG_amlodipine", "entity:API_amlodipine_bes"),
        ("entity:DRUG_amoxicillin", "entity:API_amoxicillin_trihy"),
        ("entity:DRUG_atorvastatin", "entity:API_atorvastatin_ca"),
        ("entity:DRUG_azithromycin", "entity:API_azithromycin_dihy"),
        ("entity:DRUG_carboplatin", "entity:API_carboplatin"),
        ("entity:DRUG_cephalexin", "entity:API_cephalexin_mono"),
        ("entity:DRUG_ciprofloxacin", "entity:API_ciprofloxacin_hcl"),
        ("entity:DRUG_cisplatin", "entity:API_cisplatin"),
    )
    for index, (drug_id, api_id) in enumerate(supply_specs, 1):
        if api_id not in outgoing[(drug_id, "CONTAINS_API")]:
            raise ValueError(f"missing drug-to-API edge: {drug_id} -> {api_id}")
        supplier_ids = sorted(outgoing[(api_id, "SUPPLIED_BY")])
        if not supplier_ids:
            raise ValueError(f"API has no suppliers: {api_id}")
        path_edges = [
            (drug_id, "CONTAINS_API", api_id),
            *[(api_id, "SUPPLIED_BY", supplier_id) for supplier_id in supplier_ids],
        ]
        supplier_answer = "; ".join(
            f"{by_id[row]['name']} ({by_id[row]['properties'].get('country', 'country unavailable')})"
            for row in supplier_ids
        )
        questions.append({
            "review_id": f"MH-SC{index:02d}",
            "category": "api_supply_chain",
            "question": (
                f"According to the frozen structured supply-chain snapshot, which API is linked to "
                f"{by_id[drug_id]['name']}, which manufacturers supply that API, and in which countries are they located?"
            ),
            "draft_answer": f"API: {by_id[api_id]['name']}. Suppliers: {supplier_answer}.",
            "node_ids": [drug_id, api_id, *supplier_ids],
            "edges": [by_edge[row] for row in path_edges],
        })

    regulatory_specs = (
        (
            "Through which intermediate guideline does ICH Q11 connect to ICH Q9 when following "
            "USES_PRINCIPLES_FROM and then COMPLEMENTS?",
            ["regdoc:ich_q11", "regdoc:ich_q10", "regdoc:ich_q9"],
            [("regdoc:ich_q11", "USES_PRINCIPLES_FROM", "regdoc:ich_q10"),
             ("regdoc:ich_q10", "COMPLEMENTS", "regdoc:ich_q9")],
        ),
        (
            "Which two successive principle dependencies connect ICH Q13 to ICH Q10 through ICH Q11?",
            ["regdoc:ich_q13", "regdoc:ich_q11", "regdoc:ich_q10"],
            [("regdoc:ich_q13", "USES_PRINCIPLES_FROM", "regdoc:ich_q11"),
             ("regdoc:ich_q11", "USES_PRINCIPLES_FROM", "regdoc:ich_q10")],
        ),
        (
            "Which GMP guideline is both a source of principles and a source of applied definitions for ICH Q13?",
            ["regdoc:ich_q13", "regdoc:ich_q7"],
            [("regdoc:ich_q13", "USES_PRINCIPLES_FROM", "regdoc:ich_q7"),
             ("regdoc:ich_q13", "APPLIES_DEFINITION_FROM", "regdoc:ich_q7")],
        ),
        (
            "Which validation guideline complements ICH Q14, and what regulatory topic does that guideline cover?",
            ["regdoc:ich_q14", "regdoc:ich_q2r2", "regtopic:analytical-procedure-validation"],
            [("regdoc:ich_q14", "COMPLEMENTS", "regdoc:ich_q2r2"),
             ("regdoc:ich_q2r2", "COVERS_TOPIC", "regtopic:analytical-procedure-validation")],
        ),
        (
            "Which two impurity guidelines are explicitly represented as complementary to ICH M7(R2)?",
            ["regdoc:ich_m7_r2", "regdoc:ich_q3a_r2", "regdoc:ich_q3b_r2"],
            [("regdoc:ich_m7_r2", "COMPLEMENTS", "regdoc:ich_q3a_r2"),
             ("regdoc:ich_m7_r2", "COMPLEMENTS", "regdoc:ich_q3b_r2")],
        ),
        (
            "Which guideline complements ICH Q12, and what regulatory topic is covered by that complementary guideline?",
            ["regdoc:ich_q12", "regdoc:ich_q10", "regtopic:pharmaceutical-quality-system"],
            [("regdoc:ich_q12", "COMPLEMENTS", "regdoc:ich_q10"),
             ("regdoc:ich_q10", "COVERS_TOPIC", "regtopic:pharmaceutical-quality-system")],
        ),
        (
            "Which 2025 draft guideline is represented as superseding both ICH Q1A(R2) and ICH Q1B?",
            ["regdoc:ich_q1_draft_2025", "regdoc:ich_q1a", "regdoc:ich_q1b"],
            [("regdoc:ich_q1_draft_2025", "SUPERSEDES", "regdoc:ich_q1a"),
             ("regdoc:ich_q1_draft_2025", "SUPERSEDES", "regdoc:ich_q1b")],
        ),
        (
            "Which CFR parts does the FDA cGMP guidance require compliance with, and what topic is the guidance linked to?",
            ["regdoc:fda_cgmp_guidance", "regref:21-cfr-parts-210-and-211", "regtopic:fda-pharmaceutical-cgmp-quality-systems"],
            [("regdoc:fda_cgmp_guidance", "REQUIRES_COMPLIANCE_WITH", "regref:21-cfr-parts-210-and-211"),
             ("regdoc:fda_cgmp_guidance", "COVERS_TOPIC", "regtopic:fda-pharmaceutical-cgmp-quality-systems")],
        ),
        (
            "Which two EU directives are interpreted by EMA GMP Annex 11, and what topic does Annex 11 cover?",
            ["regdoc:ema_gmp_annex_11", "regref:directive-2003-94-ec", "regref:directive-91-412-eec", "regtopic:gmp-computerized-systems"],
            [("regdoc:ema_gmp_annex_11", "INTERPRETS", "regref:directive-2003-94-ec"),
             ("regdoc:ema_gmp_annex_11", "INTERPRETS", "regref:directive-91-412-eec"),
             ("regdoc:ema_gmp_annex_11", "COVERS_TOPIC", "regtopic:gmp-computerized-systems")],
        ),
        (
            "Which API GMP guideline supplies principles to ICH Q10, and which risk-management guideline complements ICH Q10?",
            ["regdoc:ich_q10", "regdoc:ich_q7", "regdoc:ich_q9"],
            [("regdoc:ich_q10", "USES_PRINCIPLES_FROM", "regdoc:ich_q7"),
             ("regdoc:ich_q10", "COMPLEMENTS", "regdoc:ich_q9")],
        ),
    )
    for index, (question, node_ids, path_edges) in enumerate(regulatory_specs, 1):
        questions.append({
            "review_id": f"MH-RG{index:02d}",
            "category": "regulatory_logic",
            "question": question,
            "draft_answer": " | ".join(by_id[row]["name"] for row in node_ids[1:]),
            "node_ids": node_ids,
            "edges": [by_edge[row] for row in path_edges],
        })

    if len(questions) != 30 or len({row["review_id"] for row in questions}) != 30:
        raise ValueError("registry must contain 30 unique questions")
    for row in questions:
        row["nodes"] = [by_id[node_id] for node_id in row.pop("node_ids")]
        row["provenance_sources"] = sorted({
            str(node.get("properties", {}).get("provenance", {}).get("source")
                or node.get("properties", {}).get("provenance", {}).get("source_file")
                or "")
            for node in row["nodes"]
        } - {""})

    payload = {
        "schema_version": "1.0",
        "status": "draft_graph_grounded_questions_pending_independent_review",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "question_count": len(questions),
        "category_counts": {name: sum(row["category"] == name for row in questions) for name in (
            "shortage_chain", "api_supply_chain", "regulatory_logic"
        )},
        "graph": {
            "path": args.graph.resolve().relative_to(ROOT).as_posix(),
            "nodes_sha256": sha256_file(nodes_path),
            "edges_sha256": sha256_file(edges_path),
        },
        "review_rule": (
            "Confirm only when the question, answerable facts, edge semantics, and provenance shown in "
            "the frozen snapshot jointly support the complete chain. Revise partial or ambiguous chains; "
            "exclude unsupported or materially misleading chains."
        ),
        "questions": questions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": payload["category_counts"]}, indent=2))


if __name__ == "__main__":
    main()
