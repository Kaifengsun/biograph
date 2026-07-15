"""Normalize a raw openFDA drug-shortage snapshot into graph-ready JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from build_regulatory_evidence_graph import normalize_alias, structured_graph


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def stable_id(prefix: str, value: str) -> str:
    normalized = normalize_alias(value)
    if normalized:
        return f"{prefix}:{normalized.replace(' ', '-') }"
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def event_id(record: dict[str, Any]) -> str:
    identity = "|".join(str(record.get(key, "")) for key in ("package_ndc", "generic_name", "company_name", "initial_posting_date"))
    return f"fda_shortage:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}"


def load_records(snapshot: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_path = snapshot / "collection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for page in manifest.get("pages", []):
        page_path = snapshot / page["file"]
        if hashlib.sha256(page_path.read_bytes()).hexdigest() != page["sha256"]:
            raise RuntimeError(f"raw page hash mismatch: {page_path}")
        payload = json.loads(page_path.read_text(encoding="utf-8"))
        records.extend(payload.get("results") or [])
    return records, manifest


def normalize_snapshot(snapshot: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing normalized output: {output}")
    records, collection_manifest = load_records(snapshot)
    _nodes, _edges, aliases = structured_graph()
    alias_targets: dict[str, list[tuple[str, str, str]]] = {}
    for alias in aliases:
        alias_targets.setdefault(alias.alias, []).append((alias.node_id, alias.label, alias.name))

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    snapshot_id = snapshot.name

    def add_node(node_id: str, label: str, name: str, properties: dict[str, Any]) -> None:
        nodes.setdefault(node_id, {"id": node_id, "label": label, "name": name, "properties": properties})

    for record in records:
        current_event_id = event_id(record)
        generic_name = str(record.get("generic_name") or record.get("presentation") or "Unknown FDA drug shortage product")
        package_ndc = str(record.get("package_ndc") or "")
        product_key = package_ndc or generic_name
        product_id = stable_id("fda_ndc", product_key)
        company_name = str(record.get("company_name") or "Unknown FDA-reported company")
        company_id = stable_id("fda_company", company_name)
        base_provenance = {
            "snapshot_id": snapshot_id,
            "collection_manifest_sha256": hashlib.sha256((snapshot / "collection_manifest.json").read_bytes()).hexdigest(),
            "source": "openFDA drug shortages API",
            "derivation": "fda_api_record",
        }
        add_node(current_event_id, "FDA_DrugShortageEvent", generic_name, {
            "package_ndc": package_ndc,
            "generic_name": str(record.get("generic_name") or ""),
            "proprietary_name": str(record.get("proprietary_name") or ""),
            "company_name": company_name,
            "status": str(record.get("status") or ""),
            "availability": str(record.get("availability") or ""),
            "shortage_reason": str(record.get("shortage_reason") or ""),
            "initial_posting_date": str(record.get("initial_posting_date") or ""),
            "change_date": str(record.get("change_date") or ""),
            "update_date": str(record.get("update_date") or ""),
            "discontinued_date": str(record.get("discontinued_date") or ""),
            "provenance": base_provenance,
        })
        openfda = record.get("openfda") or {}
        add_node(product_id, "FDANDCProduct", package_ndc or generic_name, {
            "package_ndc": package_ndc,
            "product_ndc": openfda.get("product_ndc") or [],
            "application_number": openfda.get("application_number") or [],
            "rxcui": openfda.get("rxcui") or [],
            "unii": openfda.get("unii") or [],
            "route": openfda.get("route") or [],
            "dosage_form": str(record.get("dosage_form") or ""),
            "provenance": base_provenance,
        })
        add_node(company_id, "FDAManufacturer", company_name, {"company_name": company_name, "provenance": base_provenance})
        edges.extend([
            {"source": current_event_id, "target": product_id, "relation": "AFFECTS_NDC_PRODUCT", "properties": {"provenance": base_provenance}},
            {"source": current_event_id, "target": company_id, "relation": "REPORTED_BY", "properties": {"provenance": base_provenance}},
        ])
        ingredient_names = openfda.get("substance_name") or []
        for ingredient_name in ingredient_names:
            ingredient_name = str(ingredient_name)
            ingredient_id = stable_id("fda_ingredient", ingredient_name)
            add_node(ingredient_id, "FDAActiveIngredient", ingredient_name, {"ingredient_name": ingredient_name, "provenance": base_provenance})
            edges.append({"source": product_id, "target": ingredient_id, "relation": "HAS_ACTIVE_INGREDIENT", "properties": {"provenance": base_provenance}})
            for entity_id, entity_label, entity_name in alias_targets.get(normalize_alias(ingredient_name), []):
                edges.append({
                    "source": ingredient_id,
                    "target": f"entity:{entity_id}",
                    "relation": "SAME_AS_CANDIDATE",
                    "properties": {"match_basis": "exact_normalized_ingredient_name", "matched_value": ingredient_name, "target_label": entity_label, "target_name": entity_name, "provenance": base_provenance},
                })

    unique_edges = {(edge["source"], edge["target"], edge["relation"]): edge for edge in edges}
    output.mkdir(parents=True)
    write_jsonl(output / "fda_nodes.jsonl", sorted(nodes.values(), key=lambda row: row["id"]))
    write_jsonl(output / "fda_edges.jsonl", sorted(unique_edges.values(), key=lambda row: (row["relation"], row["source"], row["target"])))
    report = {
        "snapshot": str(snapshot),
        "record_count": len(records),
        "counts": {"nodes": len(nodes), "edges": len(unique_edges), "relations": dict(sorted(Counter(edge["relation"] for edge in unique_edges.values()).items()))},
        "canonical_artifacts_replaced": False,
    }
    write_json(output / "normalization_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize an openFDA drug-shortage snapshot")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = normalize_snapshot(Path(args.snapshot), Path(args.output))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
