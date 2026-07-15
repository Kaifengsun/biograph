"""Assemble a pre-implementation held-out review pack from frozen source assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_PROVISIONAL = Path("data/eval/three_path_evaluation_provisional_2026-07-14.json")
DEFAULT_CORPUS = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
DEFAULT_GRAPH = Path("artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda")

SLICE_OVERRIDES = {
    "gapfill:DS008": "document_structure",
    "gapfill:DS011": "document_structure",
}

NEW_TEXT_CASES = [
    {
        "annotation_id": "heldout:DS012",
        "query_slice": "document_structure",
        "query": "Which EMA GMP Annex 11 sections should be navigated to retrieve requirements for security, electronic signatures, business continuity, and archiving?",
        "suggested_gold_evidence_chunk_ids": [
            "ema_gmp_annex_11_C0016_3e81b863",
            "ema_gmp_annex_11_C0018_67f21a76",
            "ema_gmp_annex_11_C0020_5c4debda",
            "ema_gmp_annex_11_C0021_8cc96e61",
        ],
    },
    {
        "annotation_id": "heldout:DS013",
        "query_slice": "document_structure",
        "query": "Which ICH Q9 sections organize the general quality risk management process into risk assessment, risk control, risk communication, and risk review?",
        "suggested_gold_evidence_chunk_ids": [
            "ich_q9_C0013_42d036f5",
            "ich_q9_C0017_b93a1a2f",
            "ich_q9_C0019_0e732ac1",
            "ich_q9_C0020_84d86715",
            "ich_q9_C0021_d8d97253",
            "ich_q9_C0022_4083b9a5",
        ],
    },
]

NEW_GRAPH_CASES = [
    {
        "annotation_id": "heldout:SP001",
        "query": "For Eugia US LLC Azacitidine Injection (NDC 55150-393-01), what availability and shortage reason are recorded, and which ICH Q9 principles connect availability risk to patient protection and proportional risk-management effort?",
        "event_node": "fda_shortage:df0975a3be18eeb7255d",
        "path": ["fda_shortage:df0975a3be18eeb7255d", "fda_ndc:55150-393-01", "fda_ingredient:azacitidine"],
        "suggested_gold_evidence_chunk_ids": ["ich_q9_C0012_cef84513"],
    },
    {
        "annotation_id": "heldout:SP002",
        "query": "For Novo Nordisk Liraglutide Injection (NDC 0169-4060-13), what availability and shortage reason are recorded, and which ICH Q9 steps should initiate and plan the corresponding quality risk-management process?",
        "event_node": "fda_shortage:1b06f681e80c3b9b755f",
        "path": ["fda_shortage:1b06f681e80c3b9b755f", "fda_ndc:0169-4060-13", "fda_ingredient:liraglutide"],
        "suggested_gold_evidence_chunk_ids": ["ich_q9_C0016_384e4cc6"],
    },
    {
        "annotation_id": "heldout:SP003",
        "query": "For Accord Healthcare Atropine Sulfate Injection (NDC 16729-484-90), what availability and shortage reason are recorded, and how does ICH Q9 define the general risk-management process and ongoing review of planned or unplanned events?",
        "event_node": "fda_shortage:8943ad3ed0f2af8a9578",
        "path": ["fda_shortage:8943ad3ed0f2af8a9578", "fda_ndc:16729-484-90", "fda_ingredient:atropine-sulfate"],
        "suggested_gold_evidence_chunk_ids": ["ich_q9_C0013_42d036f5", "ich_q9_C0022_4083b9a5"],
    },
    {
        "annotation_id": "heldout:SP004",
        "query": "For pharmaand GmbH Peginterferon alfa-2a Injection (NDC 82154-0449-1), what availability and shortage reason are recorded, and what does ICH Q9 require for communicating and documenting risk information between relevant parties?",
        "event_node": "fda_shortage:fd6195ac159dfa6602ee",
        "path": ["fda_shortage:fd6195ac159dfa6602ee", "fda_ndc:82154-0449-1", "fda_ingredient:peginterferon-alfa-2a"],
        "suggested_gold_evidence_chunk_ids": ["ich_q9_C0020_84d86715", "ich_q9_C0021_d8d97253"],
    },
    {
        "annotation_id": "heldout:SP005",
        "query": "For Accord Healthcare Methotrexate Sodium Injection (NDC 16729-277-35), what availability and shortage reason are recorded, and how does ICH Q9 describe proactive prevention and mitigation of product-availability risks arising from supply-chain complexity?",
        "event_node": "fda_shortage:47c4d3631a8c95419e35",
        "path": ["fda_shortage:47c4d3631a8c95419e35", "fda_ndc:16729-277-35", "fda_ingredient:methotrexate"],
        "suggested_gold_evidence_chunk_ids": ["ich_q9_C0035_779828fb", "ich_q9_C0036_7fec0db2"],
    },
    {
        "annotation_id": "heldout:SP006",
        "query": "For Hikma Furosemide Oral Solution (NDC 0054-3294-50), what availability and shortage reason are recorded, and which ICH Q9 risk-assessment and risk-control questions should guide mitigation decisions?",
        "event_node": "fda_shortage:081aab155ccaa28042a4",
        "path": ["fda_shortage:081aab155ccaa28042a4", "fda_ndc:0054-3294-50", "fda_ingredient:furosemide"],
        "suggested_gold_evidence_chunk_ids": ["ich_q9_C0017_b93a1a2f", "ich_q9_C0019_0e732ac1"],
    },
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def load_chunks(corpus: Path) -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    for path in sorted(corpus.glob("*_enriched.json")):
        for row in read_json(path):
            chunk_id = str(row.get("chunk_id", ""))
            if chunk_id:
                chunks[chunk_id] = {**row, "frozen_source_file": str(path)}
    return chunks


def load_graph(graph: Path) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    nodes = {row["id"]: row for row in (json.loads(line) for line in (graph / "nodes.jsonl").read_text(encoding="utf-8").splitlines())}
    edges = {
        (row["source"], row["target"])
        for row in (json.loads(line) for line in (graph / "edges.jsonl").read_text(encoding="utf-8").splitlines())
    }
    return nodes, edges


def event_record(node: dict[str, Any]) -> dict[str, Any]:
    properties = node.get("properties") or {}
    return {
        key: properties.get(key, "")
        for key in ("generic_name", "company_name", "package_ndc", "availability", "shortage_reason", "status", "update_date")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a 30-query held-out human-review pack")
    parser.add_argument("--provisional", default=str(DEFAULT_PROVISIONAL))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing held-out pack: {output}")
    provisional_path = Path(args.provisional)
    corpus_path = Path(args.corpus)
    graph_path = Path(args.graph)
    provisional = read_json(provisional_path)
    chunks = load_chunks(corpus_path)
    nodes, edges = load_graph(graph_path)

    rows = []
    for source in provisional.get("queries") or []:
        if source.get("review_status") != "unreviewed":
            continue
        assisted = source.get("llm_assisted_review") or {}
        suggested = list(assisted.get("direct_support_chunk_ids") or [])
        candidates = unique(suggested + list(source.get("candidate_evidence_chunk_ids") or []))
        rows.append({
            "annotation_id": source["annotation_id"],
            "query": source["query"],
            "query_slice": SLICE_OVERRIDES.get(source["annotation_id"], source["query_slice"]),
            "candidate_evidence_chunk_ids": candidates,
            "suggested_gold_evidence_chunk_ids": suggested,
            "suggested_graph_path_node_ids": [],
            "structured_graph_record": None,
            "review_status": "Pending",
            "gold_evidence_chunk_ids": [],
            "accepted_graph_path_node_ids": [],
            "review_note": "",
            "origin": "remaining_unreviewed_candidate_from_2026-07-14_registry",
        })

    for source in NEW_TEXT_CASES:
        suggested = list(source["suggested_gold_evidence_chunk_ids"])
        rows.append({
            **source,
            "candidate_evidence_chunk_ids": suggested,
            "suggested_graph_path_node_ids": [],
            "structured_graph_record": None,
            "review_status": "Pending",
            "gold_evidence_chunk_ids": [],
            "accepted_graph_path_node_ids": [],
            "review_note": "",
            "origin": "preimplementation_document_structure_case",
        })

    for source in NEW_GRAPH_CASES:
        path = list(source["path"])
        if any(node_id not in nodes for node_id in path):
            raise ValueError(f"missing graph node in {source['annotation_id']}: {path}")
        if any((left, right) not in edges for left, right in zip(path, path[1:])):
            raise ValueError(f"non-contiguous directed graph path in {source['annotation_id']}: {path}")
        suggested = list(source["suggested_gold_evidence_chunk_ids"])
        rows.append({
            "annotation_id": source["annotation_id"],
            "query": source["query"],
            "query_slice": "supply_chain_evidence_path",
            "candidate_evidence_chunk_ids": suggested,
            "suggested_gold_evidence_chunk_ids": suggested,
            "suggested_graph_path_node_ids": path,
            "structured_graph_record": event_record(nodes[source["event_node"]]),
            "review_status": "Pending",
            "gold_evidence_chunk_ids": [],
            "accepted_graph_path_node_ids": [],
            "review_note": "",
            "origin": "preimplementation_openfda_structured_path_case",
        })

    if len(rows) != 30 or len({row["annotation_id"] for row in rows}) != 30:
        raise ValueError(f"expected 30 unique held-out candidates, found {len(rows)}")
    unknown_chunks = sorted({chunk_id for row in rows for chunk_id in row["candidate_evidence_chunk_ids"] if chunk_id not in chunks})
    if unknown_chunks:
        raise ValueError(f"held-out candidates refer to chunks outside frozen corpus: {unknown_chunks}")
    slices = Counter(row["query_slice"] for row in rows)
    expected = {"single_clause": 10, "table": 6, "cross_document": 4, "document_structure": 4, "supply_chain_evidence_path": 6}
    if dict(slices) != expected:
        raise ValueError(f"unexpected held-out composition: {dict(slices)}")

    result = {
        "schema_version": "1.0",
        "status": "heldout_candidate_pack_requires_human_review_do_not_execute",
        "formal_metrics_ready": False,
        "retrieval_execution_prohibited": True,
        "composition": expected,
        "protocol": "docs/experiments/adaptive_text_first_heldout_protocol_2026-07-15.md",
        "sources": {
            "provisional_registry": str(provisional_path),
            "provisional_registry_sha256": sha256_file(provisional_path),
            "frozen_corpus": str(corpus_path),
            "graph": str(graph_path),
            "graph_nodes_sha256": sha256_file(graph_path / "nodes.jsonl"),
            "graph_edges_sha256": sha256_file(graph_path / "edges.jsonl"),
        },
        "queries": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"query_count": len(rows), "composition": expected, "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
