"""Extract explicit, source-backed relations among frozen regulatory documents.

This extractor intentionally uses a small, auditable rule catalogue rather
than an LLM or topical-similarity inference. Each emitted relation carries the
literal source span that licenses it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from build_regulatory_evidence_graph import DEFAULT_SOURCE, load_corpus, normalize_alias, sha256_file


DEFAULT_MARKDOWN_ROOT = Path("data/markdown")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def stable_node_id(prefix: str, value: str) -> str:
    normalized = normalize_alias(value).replace(" ", "-")
    if normalized:
        return f"{prefix}:{normalized}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def markdown_path(markdown_root: Path, doc_id: str) -> Path:
    aliases = {
        "ich_q1_draft_2025": "ich_q1_draft2025",
        "ema_gmp_annex_11": "ema_gmp_annex11",
    }
    source_id = aliases.get(doc_id, doc_id)
    path = markdown_root / source_id / f"{source_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"markdown source missing for frozen document {doc_id}: {path}")
    return path


@dataclass(frozen=True)
class RelationRule:
    rule_id: str
    source_doc_id: str
    relation: str
    target_kind: str
    target_value: str
    evidence_pattern: str


# These rules intentionally correspond to literal statements in the supplied
# regulatory texts. They are not semantic guesses from a citation list.
RELATION_RULES: tuple[RelationRule, ...] = (
    RelationRule("REL-Q1-001", "ich_q1_draft_2025", "SUPERSEDES", "doc", "ich_q1a", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q1-002", "ich_q1_draft_2025", "SUPERSEDES", "doc", "ich_q1b", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q1-003", "ich_q1_draft_2025", "SUPERSEDES", "doc", "ich_q1c", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q1-004", "ich_q1_draft_2025", "SUPERSEDES", "doc", "ich_q1d", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q1-005", "ich_q1_draft_2025", "SUPERSEDES", "doc", "ich_q1e", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q1-006", "ich_q1_draft_2025", "SUPERSEDES", "external", "ICH Q1F", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q1-007", "ich_q1_draft_2025", "SUPERSEDES", "external", "ICH Q5C", r"supersedes\s+ICH\s+Q1A-F\s+and\s+Q5C",),
    RelationRule("REL-Q12-001", "ich_q12", "COMPLEMENTS", "doc", "ich_q10", r"complements\s+and\s+adds\s+to.*?ICH\s+Q8\(R2\)\s+and\s+Q10\s+Annex\s+1",),
    RelationRule("REL-Q13-001", "ich_q13", "APPLIES_DEFINITION_FROM", "doc", "ich_q7", r"ICH\s+Q7\s+definition\s+of\s+a\s+batch\s+is\s+applicable",),
    RelationRule("REL-Q13-002", "ich_q13", "USES_PRINCIPLES_FROM", "doc", "ich_q7", r"principles\s+outlined\s+in\s+ICH\s+Q7,\s+Q8,\s+Q10\s+and\s+Q11,\s+and\s+quality\s+risk\s+management\s+described\s+in\s+ICH\s+Q9",),
    RelationRule("REL-Q13-003", "ich_q13", "USES_PRINCIPLES_FROM", "doc", "ich_q9", r"principles\s+outlined\s+in\s+ICH\s+Q7,\s+Q8,\s+Q10\s+and\s+Q11,\s+and\s+quality\s+risk\s+management\s+described\s+in\s+ICH\s+Q9",),
    RelationRule("REL-Q13-004", "ich_q13", "USES_PRINCIPLES_FROM", "doc", "ich_q10", r"principles\s+outlined\s+in\s+ICH\s+Q7,\s+Q8,\s+Q10\s+and\s+Q11,\s+and\s+quality\s+risk\s+management\s+described\s+in\s+ICH\s+Q9",),
    RelationRule("REL-Q13-005", "ich_q13", "USES_PRINCIPLES_FROM", "doc", "ich_q11", r"principles\s+outlined\s+in\s+ICH\s+Q7,\s+Q8,\s+Q10\s+and\s+Q11,\s+and\s+quality\s+risk\s+management\s+described\s+in\s+ICH\s+Q9",),
    RelationRule("REL-Q14-001", "ich_q14", "COMPLEMENTS", "doc", "ich_q2r2", r"This\s+guideline\s+complements\s+ICH\s+Q2\s+Validation\s+of\s+Analytical\s+Procedures",),
    RelationRule("REL-Q10-001", "ich_q10", "COMPLEMENTS", "doc", "ich_q9", r"complements\s+ICH\s+Q8.*?and\s+ICH\s+Q9",),
    RelationRule("REL-Q10-002", "ich_q10", "USES_PRINCIPLES_FROM", "doc", "ich_q7", r"ICH\s+Q7\s+Guideline.*?form\s+the\s+foundation\s+for\s+ICH\s+Q10",),
    RelationRule("REL-Q11-001", "ich_q11", "USES_PRINCIPLES_FROM", "doc", "ich_q9", r"Quality\s+Risk\s+Management\s+\(QRM,\s+as\s+described\s+in\s+ICH\s+Q9\)",),
    RelationRule("REL-Q11-002", "ich_q11", "USES_PRINCIPLES_FROM", "doc", "ich_q10", r"Knowledge\s+management\s+\(as\s+described\s+in\s+ICH\s+Q10\)",),
    RelationRule("REL-M7-001", "ich_m7_r2", "COMPLEMENTS", "doc", "ich_q3a_r2", r"This\s+guideline\s+is\s+intended\s+to\s+complement\s+ICH\s+Q3A\(R2\),\s+Q3B\(R2\)",),
    RelationRule("REL-M7-002", "ich_m7_r2", "COMPLEMENTS", "doc", "ich_q3b_r2", r"This\s+guideline\s+is\s+intended\s+to\s+complement\s+ICH\s+Q3A\(R2\),\s+Q3B\(R2\)",),
    RelationRule("REL-FDA-001", "fda_cgmp_guidance", "REQUIRES_COMPLIANCE_WITH", "external", "21 CFR Parts 210 and 211", r"refer\s+to\s+parts\s+210\s+and\s+211\s+to\s+ensure\s+full\s+compliance",),
    RelationRule("REL-EMA-001", "ema_gmp_annex_11", "INTERPRETS", "external", "Directive 2003/94/EC", r"guidance\s+for\s+the\s+interpretation.*?Directive\s+2003/94/EC",),
    RelationRule("REL-EMA-002", "ema_gmp_annex_11", "INTERPRETS", "external", "Directive 91/412/EEC", r"guidance\s+for\s+the\s+interpretation.*?Directive\s+91/412/EEC",),
)


TOPIC_RULES: tuple[RelationRule, ...] = (
    RelationRule("TOPIC-Q1", "ich_q1_draft_2025", "COVERS_TOPIC", "topic", "Drug substance and product stability", r"stability\s+data\s+expectations\s+for\s+drug\s+substances\s+and\s+drug\s+products",),
    RelationRule("TOPIC-Q7", "ich_q7", "COVERS_TOPIC", "topic", "Good manufacturing practice for active pharmaceutical ingredients", r"Good\s+Manufacturing\s+Practice\s+Guide\s+for\s+Active\s+Pharmaceutical\s+Ingredients",),
    RelationRule("TOPIC-Q9", "ich_q9", "COVERS_TOPIC", "topic", "Pharmaceutical quality risk management", r"systematic\s+approach\s+to\s+quality\s+risk\s+management",),
    RelationRule("TOPIC-Q10", "ich_q10", "COVERS_TOPIC", "topic", "Pharmaceutical quality system", r"model\s+for\s+an\s+effective\s+pharmaceutical\s+quality\s+system",),
    RelationRule("TOPIC-Q11", "ich_q11", "COVERS_TOPIC", "topic", "Drug substance development and manufacture", r"development\s+and\s+manufacture\s+that\s+pertain\s+to\s+drug\s+substance",),
    RelationRule("TOPIC-Q12", "ich_q12", "COVERS_TOPIC", "topic", "Post-approval CMC change management", r"commercial\s+phase\s+of\s+the\s+product\s+lifecycle",),
    RelationRule("TOPIC-Q13", "ich_q13", "COVERS_TOPIC", "topic", "Continuous manufacturing", r"development,\s+implementation,\s+operation,\s+and\s+lifecycle\s+management\s+of\s+continuous\s+manufacturing",),
    RelationRule("TOPIC-Q14", "ich_q14", "COVERS_TOPIC", "topic", "Analytical procedure development", r"developing\s+and\s+maintaining\s+analytical\s+procedures",),
    RelationRule("TOPIC-Q2", "ich_q2r2", "COVERS_TOPIC", "topic", "Analytical procedure validation", r"validation\s+of\s+analytical\s+procedures",),
    RelationRule("TOPIC-M7", "ich_m7_r2", "COVERS_TOPIC", "topic", "Mutagenic impurity assessment and control", r"assessment\s+and\s+control\s+of\s+DNA\s+reactive.*?mutagenic\s+impurities",),
    RelationRule("TOPIC-FDA", "fda_cgmp_guidance", "COVERS_TOPIC", "topic", "FDA pharmaceutical cGMP quality systems", r"quality\s+systems\s+and\s+risk\s+management\s+approaches.*?CGMP\s+regulations",),
    RelationRule("TOPIC-EMA", "ema_gmp_annex_11", "COVERS_TOPIC", "topic", "GMP computerized systems", r"Computerised\s+Systems",),
)


def target_node(rule: RelationRule, frozen_docs: set[str]) -> dict[str, Any]:
    if rule.target_kind == "doc":
        if rule.target_value not in frozen_docs:
            raise ValueError(f"rule target not present in frozen corpus: {rule.target_value}")
        return {"id": f"regdoc:{rule.target_value}", "nodes": []}
    if rule.target_kind == "topic":
        node_id = stable_node_id("regtopic", rule.target_value)
        return {
            "id": node_id,
            "nodes": [{"id": node_id, "label": "RegulatoryTopic", "name": rule.target_value, "properties": {"topic_name": rule.target_value}}],
        }
    if rule.target_kind == "external":
        node_id = stable_node_id("regref", rule.target_value)
        return {
            "id": node_id,
            "nodes": [{"id": node_id, "label": "RegulatoryReference", "name": rule.target_value, "properties": {"reference_name": rule.target_value}}],
        }
    raise ValueError(f"unsupported target kind: {rule.target_kind}")


def extract_rules(
    rules: Iterable[RelationRule],
    frozen_docs: set[str],
    markdown_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    cache: dict[str, tuple[Path, str, str]] = {}

    for rule in rules:
        if rule.source_doc_id not in frozen_docs:
            audit.append({"rule_id": rule.rule_id, "status": "skipped_source_not_in_frozen_corpus"})
            continue
        if rule.source_doc_id not in cache:
            path = markdown_path(markdown_root, rule.source_doc_id)
            text = path.read_text(encoding="utf-8", errors="ignore")
            cache[rule.source_doc_id] = (path, text, sha256_file(path))
        path, text, source_hash = cache[rule.source_doc_id]
        match = re.search(rule.evidence_pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            audit.append({"rule_id": rule.rule_id, "status": "rejected_evidence_not_found", "source_doc_id": rule.source_doc_id})
            continue
        target = target_node(rule, frozen_docs)
        for node in target["nodes"]:
            node["properties"]["provenance"] = {
                "source_file": str(path),
                "source_file_sha256": source_hash,
                "derivation": "explicit_text_relation_target",
            }
            nodes[node["id"]] = node
        evidence = match.group(0)
        edges.append({
            "source": f"regdoc:{rule.source_doc_id}",
            "target": target["id"],
            "relation": rule.relation,
            "properties": {
                "rule_id": rule.rule_id,
                "evidence_text": evidence,
                "match_start": match.start(),
                "match_end": match.end(),
                "provenance": {
                    "source_file": str(path),
                    "source_file_sha256": source_hash,
                    "source_locator": f"char:{match.start()}-{match.end()}",
                    "derivation": "explicit_text_relation",
                },
            },
        })
        audit.append({"rule_id": rule.rule_id, "status": "accepted", "source_doc_id": rule.source_doc_id, "target": target["id"]})
    return sorted(nodes.values(), key=lambda row: row["id"]), sorted(edges, key=lambda row: (row["relation"], row["source"], row["target"])), audit


def extract_document_relations(source: Path, markdown_root: Path, output: Path) -> dict[str, Any]:
    documents, _paths = load_corpus(source)
    frozen_docs = set(documents)
    nodes, edges, audit = extract_rules((*RELATION_RULES, *TOPIC_RULES), frozen_docs, markdown_root)
    output.mkdir(parents=True)
    write_jsonl(output / "relation_nodes.jsonl", nodes)
    write_jsonl(output / "relation_edges.jsonl", edges)
    report = {
        "source": str(source),
        "markdown_root": str(markdown_root),
        "counts": {"nodes": len(nodes), "edges": len(edges), "relations": dict(sorted(Counter(edge["relation"] for edge in edges).items()))},
        "rules": {"configured": len(RELATION_RULES) + len(TOPIC_RULES), "accepted": sum(item["status"] == "accepted" for item in audit), "rejected": sum(item["status"] != "accepted" for item in audit)},
        "canonical_artifacts_replaced": False,
    }
    write_json(output / "relation_extraction_report.json", report)
    write_json(output / "relation_extraction_audit.json", audit)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract explicit regulatory-document relations")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--markdown-root", default=str(DEFAULT_MARKDOWN_ROOT))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing relation output: {output}")
    report = extract_document_relations(Path(args.source), Path(args.markdown_root), output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
