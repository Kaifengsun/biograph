"""Build a provenance-preserving graph snapshot from the frozen regulatory corpus.

The output is a staging artifact, not a Neo4j import and not a replacement for
the existing graph. It materializes document hierarchy, tables, exact entity
mentions, and explicit regulatory references for later retrieval experiments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SOURCE = Path("data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
DEFAULT_OUTPUT = Path("artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4")
FDA_ENRICHMENT_SOURCE = Path("data/fda_enrichment_data.json")
GRAPH_VERSION = "regulatory-evidence-graph-v1"


@dataclass(frozen=True)
class EntityAlias:
    node_id: str
    label: str
    name: str
    alias: str


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"expected JSON object in {path}:{line_number}")
        rows.append(row)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def doc_node_id(doc_id: str) -> str:
    return f"regdoc:{doc_id}"


def chunk_node_id(chunk_id: str) -> str:
    return f"chunk:{chunk_id}"


def table_node_id(doc_id: str, chunk_id: str, index: int) -> str:
    return f"table:{doc_id}:{chunk_id}:{index:03d}"


def normalize_alias(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def display_title(doc_id: str, rows: list[dict[str, Any]]) -> str:
    metadata = rows[0].get("metadata") or {}
    for key in ("title", "document_title", "source_title"):
        if metadata.get(key):
            return str(metadata[key])
    for row in rows:
        heading = str(row.get("heading", "")).strip()
        if heading and len(heading) > 12:
            return heading
    return doc_id.replace("_", " ")


def provenance(source_file: str, locator: str, derivation: str) -> dict[str, str]:
    return {
        "graph_version": GRAPH_VERSION,
        "source_file": source_file,
        "source_locator": locator,
        "derivation": derivation,
    }


def load_corpus(source: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Path]]:
    docs: dict[str, list[dict[str, Any]]] = {}
    paths: dict[str, Path] = {}
    for path in sorted(source.glob("*_enriched.json")):
        rows = read_json(path)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"expected non-empty chunk list: {path}")
        doc_ids = {str(row.get("doc_id", "")) for row in rows}
        if len(doc_ids) != 1 or not next(iter(doc_ids)):
            raise ValueError(f"invalid doc_id set in {path}: {doc_ids}")
        doc_id = next(iter(doc_ids))
        if doc_id in docs:
            raise ValueError(f"duplicate document artifact: {doc_id}")
        docs[doc_id] = rows
        paths[doc_id] = path
    if not docs:
        raise RuntimeError(f"no enriched files found in {source}")
    return docs, paths


def hierarchy_edges(rows: list[dict[str, Any]], source_file: str) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    """Infer one structural parent per chunk from parser order and heading level."""
    doc_id = str(rows[0]["doc_id"])
    parents: dict[str, str] = {}
    edges: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []

    for row in rows:
        chunk_id = str(row["chunk_id"])
        level = int(row.get("level") or 1)
        while stack and int(stack[-1].get("level") or 1) >= level:
            stack.pop()

        target = chunk_node_id(chunk_id)
        if level <= 1 or not stack:
            source = doc_node_id(doc_id)
            relation = "CONTAINS"
            derivation = "document_root_or_no_lower_level_parent"
        else:
            parent_chunk = str(stack[-1]["chunk_id"])
            source = chunk_node_id(parent_chunk)
            relation = "PARENT_OF"
            parents[chunk_id] = parent_chunk
            derivation = "hierarchy_inference_from_parser_order_and_level"

        edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "properties": {
                "child_level": level,
                "parent_heading": stack[-1].get("heading", "") if stack and relation == "PARENT_OF" else "",
                "provenance": provenance(source_file, chunk_id, derivation),
            },
        })
        if relation == "CONTAINS" and level > 1:
            audits.append({
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "level": level,
                "reason": "no_preceding_lower_level_chunk",
            })
        stack.append(row)

    return edges, parents, audits


def next_edges(rows: list[dict[str, Any]], source_file: str, known_ids: set[str]) -> list[dict[str, Any]]:
    edges = []
    for row in rows:
        chunk_id = str(row["chunk_id"])
        next_id = str(row.get("next_chunk_id") or "")
        if next_id and next_id in known_ids:
            edges.append({
                "source": chunk_node_id(chunk_id),
                "target": chunk_node_id(next_id),
                "relation": "NEXT",
                "properties": {
                    "provenance": provenance(source_file, chunk_id, "parser_provided_next_chunk_id"),
                },
            })
    return edges


def structured_graph() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[EntityAlias]]:
    """Load typed supply-chain entities as structured-source context, not regulatory proof."""
    from pharma_supply_chain import core_data

    node_groups = {
        "Drug": ("DRUGS", "DRUGS_EXPANSION"),
        "API": ("APIS", "APIS_EXPANSION"),
        "Manufacturer": ("MANUFACTURERS", "MANUFACTURERS_EXPANSION"),
        "Country": ("COUNTRIES", "COUNTRIES_EXPANSION"),
        "TherapeuticArea": ("THERAPEUTIC_AREAS", "THERAPEUTIC_AREAS_EXPANSION"),
        "Regulation": ("REGULATIONS", "REGULATIONS_EXPANSION"),
        "ShortageEvent": ("SHORTAGE_EVENTS", "SHORTAGE_EVENTS_EXPANSION"),
    }
    nodes: list[dict[str, Any]] = []
    aliases: list[EntityAlias] = []
    seen_ids: set[str] = set()

    for label, constants in node_groups.items():
        for constant in constants:
            for row in getattr(core_data, constant, []):
                if not isinstance(row, dict) or not row.get("id") or not row.get("name"):
                    continue
                entity_id = str(row["id"])
                if entity_id in seen_ids:
                    continue
                seen_ids.add(entity_id)
                nodes.append({
                    "id": f"entity:{entity_id}",
                    "label": label,
                    "name": str(row["name"]),
                    "properties": {
                        **{k: v for k, v in row.items() if k not in {"id", "name"}},
                        "provenance": {
                            "graph_version": GRAPH_VERSION,
                            "source_file": "pharma_supply_chain/core_data.py",
                            "source_locator": entity_id,
                            "derivation": "structured_supply_chain_source",
                        },
                    },
                })
                raw_name = str(row["name"])
                for alias in {raw_name, normalize_alias(raw_name)}:
                    normalized = normalize_alias(alias)
                    if len(normalized) >= 4:
                        aliases.append(EntityAlias(entity_id, label, raw_name, normalized))

    edges: list[dict[str, Any]] = []
    relation_groups = (
        ("DRUG_API_MAP", "DRUGS_EXPANSION", "APIS_EXPANSION", "CONTAINS_API"),
        ("API_SUPPLIER_MAP", "APIS_EXPANSION", "MANUFACTURERS_EXPANSION", "SUPPLIED_BY"),
        ("API_SUBSTITUTES", "APIS_EXPANSION", "APIS_EXPANSION", "SUBSTITUTE_OF"),
        ("DRUG_INTERACTIONS", "DRUGS_EXPANSION", "DRUGS_EXPANSION", "INTERACTS_WITH"),
    )
    for constant, _source_group, _target_group, relation in relation_groups:
        for row in getattr(core_data, constant, []):
            if not isinstance(row, (tuple, list)) or len(row) < 2:
                continue
            edges.append({
                "source": f"entity:{row[0]}",
                "target": f"entity:{row[1]}",
                "relation": relation,
                "properties": {
                    "provenance": {
                        "graph_version": GRAPH_VERSION,
                        "source_file": "pharma_supply_chain/core_data.py",
                        "source_locator": constant,
                        "derivation": "structured_supply_chain_source",
                    },
                },
            })
    for drug_id, area_id in getattr(core_data, "DRUG_AREA_MAP", {}).items():
        # Some legacy mappings use a therapeutic drug class rather than a
        # concrete Drug entity as the source. Materialize that class so the
        # relation never creates a dangling endpoint.
        if drug_id not in seen_ids:
            seen_ids.add(drug_id)
            nodes.append({
                "id": f"entity:{drug_id}",
                "label": "DrugClass",
                "name": str(drug_id).replace("_", " "),
                "properties": {
                    "class_id": str(drug_id),
                    "provenance": {
                        "graph_version": GRAPH_VERSION,
                        "source_file": "pharma_supply_chain/core_data.py",
                        "source_locator": "DRUG_AREA_MAP",
                        "derivation": "structured_drug_class_from_therapeutic_area_map",
                    },
                },
            })
        edges.append({
            "source": f"entity:{drug_id}",
            "target": f"entity:{area_id}",
            "relation": "BELONGS_TO_AREA",
            "properties": {
                "provenance": {
                    "graph_version": GRAPH_VERSION,
                    "source_file": "pharma_supply_chain/core_data.py",
                    "source_locator": "DRUG_AREA_MAP",
                    "derivation": "structured_supply_chain_source",
                },
            },
        })
    return nodes, edges, aliases


def fda_enforcement_graph(existing_aliases: list[EntityAlias]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[EntityAlias]]:
    """Add dated FDA enforcement records as factual signal nodes with provenance."""
    if not FDA_ENRICHMENT_SOURCE.exists():
        return [], [], []
    data = read_json(FDA_ENRICHMENT_SOURCE)
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {FDA_ENRICHMENT_SOURCE}")

    drug_aliases = {
        alias.alias: alias for alias in existing_aliases if alias.label == "Drug"
    }
    manufacturer_aliases = {
        alias.alias: alias for alias in existing_aliases if alias.label == "Manufacturer"
    }
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    aliases: list[EntityAlias] = []

    def ensure_fda_entity(label: str, name: str, source_locator: str) -> str:
        digest = hashlib.sha256(f"{label}|{name}".encode("utf-8")).hexdigest()[:16]
        node_id = f"entity:fda:{label.lower()}:{digest}"
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "label": label,
                "name": name,
                "properties": {
                    "provenance": {
                        "graph_version": GRAPH_VERSION,
                        "source_file": str(FDA_ENRICHMENT_SOURCE),
                        "source_locator": source_locator,
                        "derivation": "fda_enrichment_record",
                    },
                },
            }
            normalized = normalize_alias(name)
            if len(normalized) >= 4:
                aliases.append(EntityAlias(node_id.removeprefix("entity:"), label, name, normalized))
        return node_id

    for drug_key, record in sorted(data.items()):
        if not isinstance(record, dict):
            continue
        label = record.get("label") or {}
        drug_name = str(label.get("drug_name") or drug_key)
        drug_alias = drug_aliases.get(normalize_alias(drug_name))
        drug_node = f"entity:{drug_alias.node_id}" if drug_alias else ensure_fda_entity("Drug", drug_name, drug_key)
        for enforcement in record.get("enforcement") or []:
            if not isinstance(enforcement, dict):
                continue
            recall_number = str(enforcement.get("recall_number") or "").strip()
            if not recall_number:
                continue
            recall_node = f"recall:{hashlib.sha256(recall_number.encode('utf-8')).hexdigest()[:16]}"
            nodes.setdefault(recall_node, {
                "id": recall_node,
                "label": "RecallEvent",
                "name": recall_number,
                "properties": {
                    "recall_number": recall_number,
                    "reason": str(enforcement.get("reason") or ""),
                    "classification": str(enforcement.get("classification") or ""),
                    "status": str(enforcement.get("status") or ""),
                    "report_date": str(enforcement.get("report_date") or ""),
                    "recalling_firm": str(enforcement.get("recalling_firm") or ""),
                    "city": str(enforcement.get("city") or ""),
                    "country": str(enforcement.get("country") or ""),
                    "provenance": {
                        "graph_version": GRAPH_VERSION,
                        "source_file": str(FDA_ENRICHMENT_SOURCE),
                        "source_locator": recall_number,
                        "derivation": "fda_enrichment_record",
                    },
                },
            })
            edges.append({
                "source": drug_node,
                "target": recall_node,
                "relation": "WAS_RECALLED",
                "properties": {
                    "provenance": {
                        "graph_version": GRAPH_VERSION,
                        "source_file": str(FDA_ENRICHMENT_SOURCE),
                        "source_locator": recall_number,
                        "derivation": "fda_enrichment_record",
                    },
                },
            })
            firm = str(enforcement.get("recalling_firm") or "").strip()
            if firm:
                known_firm = manufacturer_aliases.get(normalize_alias(firm))
                firm_node = f"entity:{known_firm.node_id}" if known_firm else ensure_fda_entity("Manufacturer", firm, recall_number)
                edges.append({
                    "source": recall_node,
                    "target": firm_node,
                    "relation": "RECALLED_BY",
                    "properties": {
                        "provenance": {
                            "graph_version": GRAPH_VERSION,
                            "source_file": str(FDA_ENRICHMENT_SOURCE),
                            "source_locator": recall_number,
                            "derivation": "fda_enrichment_record",
                        },
                    },
                })
    return list(nodes.values()), edges, aliases


def exact_entity_mentions(
    rows: list[dict[str, Any]], source_file: str, aliases: list[EntityAlias]
) -> list[dict[str, Any]]:
    alias_map: dict[str, list[EntityAlias]] = defaultdict(list)
    for alias in aliases:
        alias_map[alias.alias].append(alias)
    patterns = [
        (alias, re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", re.I))
        for alias in sorted(alias_map, key=len, reverse=True)
    ]
    edges: list[dict[str, Any]] = []
    for row in rows:
        text = " ".join(str(row.get(key, "")) for key in ("heading", "content"))
        normalized_text = normalize_alias(text)
        for alias, pattern in patterns:
            match = pattern.search(normalized_text)
            if not match:
                continue
            for entity in alias_map[alias]:
                edges.append({
                    "source": chunk_node_id(str(row["chunk_id"])),
                    "target": f"entity:{entity.node_id}",
                    "relation": "MENTIONS",
                    "properties": {
                        "matched_alias": alias,
                        "match_start": match.start(),
                        "match_end": match.end(),
                        "link_confidence": "exact_normalized_alias",
                        "provenance": provenance(source_file, str(row["chunk_id"]), "exact_alias_linker"),
                    },
                })
    return edges


def reference_catalog(documents: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    base_candidates: dict[str, list[str]] = defaultdict(list)
    for doc_id in documents:
        if doc_id.startswith("ich_"):
            code = doc_id[4:].upper().replace("_", "")
            code = re.sub(r"R(\d+)$", r"(R\1)", code)
            catalog[f"ICH {code}"] = doc_id
            base_match = re.match(r"(Q\d+[A-Z]?|M\d+)", code)
            if base_match:
                base_candidates[f"ICH {base_match.group(1)}"].append(doc_id)
        elif doc_id == "ema_gmp_annex_11":
            catalog["EMA GMP ANNEX 11"] = doc_id
            catalog["ANNEX 11"] = doc_id
        elif doc_id == "fda_cgmp_guidance":
            catalog["FDA CGMP"] = doc_id
            catalog["FDA CGMP GUIDANCE"] = doc_id
        elif doc_id == "who_stability_q1f":
            catalog["WHO Q1F"] = doc_id
    # Add an unversioned alias only when exactly one frozen document can own it.
    for alias, candidates in base_candidates.items():
        if len(candidates) == 1:
            catalog[alias] = candidates[0]
    return catalog


REFERENCE_RE = re.compile(
    r"\b(?:ICH\s+(?:GUIDELINE\s+)?[QM]\d+[A-Z]?(?:\s*\(R\d+\)|R\d+)?|"
    r"EMA\s+GMP\s+ANNEX\s+\d+|ANNEX\s+\d+|FDA\s+CGMP(?:\s+GUIDANCE)?|"
    r"WHO\s+Q1F|21\s+CFR(?:\s+PART)?\s+\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


def explicit_references(
    rows: list[dict[str, Any]], source_file: str, catalog: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    unresolved_nodes: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_chunk = str(row["chunk_id"])
        text = " ".join(str(row.get(key, "")) for key in ("heading", "content"))
        for match in REFERENCE_RE.finditer(text):
            raw = match.group(0)
            canonical = re.sub(r"\s+", " ", raw.upper()).strip()
            target_doc = catalog.get(canonical)
            if target_doc == row.get("doc_id"):
                continue
            if target_doc:
                target = doc_node_id(target_doc)
            else:
                ref_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
                target = f"regref:{ref_id}"
                unresolved_nodes.setdefault(target, {
                    "id": target,
                    "label": "RegulatoryReference",
                    "name": canonical,
                    "properties": {
                        "provenance": provenance(source_file, source_chunk, "explicit_reference_unresolved_in_corpus"),
                    },
                })
            edges.append({
                "source": chunk_node_id(source_chunk),
                "target": target,
                "relation": "REFERENCES",
                "properties": {
                    "reference_text": raw,
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "provenance": provenance(source_file, source_chunk, "explicit_reference_regex"),
                },
            })
    return edges, list(unresolved_nodes.values())


def table_nodes_and_edges(source: Path, documents: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    known_chunks = {str(row["chunk_id"]) for rows in documents.values() for row in rows}
    for path in sorted(source.glob("*_tables.json")):
        doc_id = path.name.removesuffix("_tables.json")
        tables = read_json(path)
        for index, table in enumerate(tables, 1):
            chunk_id = str(table.get("chunk_id") or "")
            table_id = table_node_id(doc_id, chunk_id or "unlinked", index)
            raw_table = str(table.get("table") or "")
            nodes.append({
                "id": table_id,
                "label": "Table",
                "name": f"{doc_id} table {index}",
                "properties": {
                    "doc_id": doc_id,
                    "table_index": index,
                    "table_summary": str(table.get("table_summary") or ""),
                    "table_sha256": hashlib.sha256(raw_table.encode("utf-8")).hexdigest(),
                    "provenance": provenance(path.name, chunk_id or f"table:{index}", "source_table_artifact"),
                },
            })
            if chunk_id in known_chunks:
                edges.append({
                    "source": chunk_node_id(chunk_id),
                    "target": table_id,
                    "relation": "HAS_TABLE",
                    "properties": {
                        "provenance": provenance(path.name, chunk_id, "table_parent_chunk_id"),
                    },
                })
            else:
                unresolved.append({
                    "source_file": path.name,
                    "table_index": index,
                    "chunk_id": chunk_id,
                    "reason": "table_parent_chunk_missing_from_frozen_corpus",
                })
    return nodes, edges, unresolved


def dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (edge["source"], edge["target"], edge["relation"])
        if key not in merged:
            merged[key] = edge
    return sorted(merged.values(), key=lambda edge: (edge["relation"], edge["source"], edge["target"]))


def build_snapshot(
    source: Path,
    output: Path,
    extra_node_files: Iterable[Path] = (),
    extra_edge_files: Iterable[Path] = (),
) -> dict[str, Any]:
    documents, paths = load_corpus(source)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    hierarchy_fallbacks: list[dict[str, Any]] = []

    for doc_id, rows in sorted(documents.items()):
        source_file = paths[doc_id].name
        nodes.append({
            "id": doc_node_id(doc_id),
            "label": "RegulatoryDocument",
            "name": display_title(doc_id, rows),
            "properties": {
                "doc_id": doc_id,
                "chunk_count": len(rows),
                "provenance": provenance(source_file, doc_id, "frozen_enriched_corpus"),
            },
        })
        for row in rows:
            nodes.append({
                "id": chunk_node_id(str(row["chunk_id"])),
                "label": "DocChunk",
                "name": str(row.get("heading") or row["chunk_id"]),
                "properties": {
                    "chunk_id": str(row["chunk_id"]),
                    "doc_id": doc_id,
                    "heading": str(row.get("heading") or ""),
                    "level": int(row.get("level") or 0),
                    "parents_context": str(row.get("parents_context") or ""),
                    "char_count": int(row.get("char_count") or 0),
                    "children_count_reported": int(row.get("children_count") or 0),
                    "has_table": bool(row.get("has_table")),
                    "summary": str(row.get("summary") or ""),
                    "provenance": provenance(source_file, str(row["chunk_id"]), "frozen_enriched_corpus"),
                },
            })
        hierarchy, _parents, fallbacks = hierarchy_edges(rows, source_file)
        edges.extend(hierarchy)
        hierarchy_fallbacks.extend(fallbacks)
        known_ids = {str(row["chunk_id"]) for row in rows}
        edges.extend(next_edges(rows, source_file, known_ids))

    structured_nodes, structured_edges, aliases = structured_graph()
    nodes.extend(structured_nodes)
    edges.extend(structured_edges)
    fda_nodes, fda_edges, fda_aliases = fda_enforcement_graph(aliases)
    nodes.extend(fda_nodes)
    edges.extend(fda_edges)
    aliases.extend(fda_aliases)

    catalog = reference_catalog(documents)
    for doc_id, rows in documents.items():
        source_file = paths[doc_id].name
        edges.extend(exact_entity_mentions(rows, source_file, aliases))
        ref_edges, ref_nodes = explicit_references(rows, source_file, catalog)
        edges.extend(ref_edges)
        nodes.extend(ref_nodes)

    tables, table_edges, unresolved_tables = table_nodes_and_edges(source, documents)
    nodes.extend(tables)
    edges.extend(table_edges)

    attachment_paths = []
    for path in extra_node_files:
        if not path.exists():
            raise FileNotFoundError(path)
        extra_nodes = read_jsonl(path)
        for node in extra_nodes:
            if not {"id", "label", "name", "properties"}.issubset(node):
                raise ValueError(f"invalid attached graph node: {path}")
        nodes.extend(extra_nodes)
        attachment_paths.append(str(path))
    for path in extra_edge_files:
        if not path.exists():
            raise FileNotFoundError(path)
        extra_edges = read_jsonl(path)
        for edge in extra_edges:
            if not {"source", "target", "relation", "properties"}.issubset(edge):
                raise ValueError(f"invalid attached graph edge: {path}")
        edges.extend(extra_edges)
        attachment_paths.append(str(path))

    unique_nodes = {node["id"]: node for node in nodes}
    unique_edges = dedupe_edges(edges)
    dangling_edges = [edge for edge in unique_edges if edge["source"] not in unique_nodes or edge["target"] not in unique_nodes]
    if dangling_edges:
        raise ValueError(f"attached graph data introduced {len(dangling_edges)} dangling edge endpoints")
    output.mkdir(parents=True)
    write_jsonl(output / "nodes.jsonl", sorted(unique_nodes.values(), key=lambda node: node["id"]))
    write_jsonl(output / "edges.jsonl", unique_edges)

    relation_counts = Counter(edge["relation"] for edge in unique_edges)
    mention_sources = {edge["source"] for edge in unique_edges if edge["relation"] == "MENTIONS"}
    chunk_nodes = [node for node in unique_nodes.values() if node["label"] == "DocChunk"]
    hierarchy_edges_count = relation_counts["CONTAINS"] + relation_counts["PARENT_OF"]
    report = {
        "graph_version": GRAPH_VERSION,
        "source": str(source),
        "output": str(output),
        "source_file_sha256": {path.name: sha256_file(path) for path in sorted(source.glob("*_enriched.json"))},
        "attachments": attachment_paths,
        "counts": {
            "documents": len(documents),
            "doc_chunks": len(chunk_nodes),
            "nodes": len(unique_nodes),
            "edges": len(unique_edges),
            "relations": dict(sorted(relation_counts.items())),
            "chunks_with_exact_entity_mentions": len(mention_sources),
            "exact_entity_mention_coverage": round(len(mention_sources) / len(chunk_nodes), 4) if chunk_nodes else 0.0,
            "hierarchy_edges": hierarchy_edges_count,
            "hierarchy_fallbacks": len(hierarchy_fallbacks),
            "unresolved_table_parents": len(unresolved_tables),
        },
        "relation_semantics": {
            "CONTAINS": "Document-to-root-or-fallback chunk membership.",
            "PARENT_OF": "Derived from frozen parser order and heading levels.",
            "NEXT": "Parser-provided neighboring chunk sequence.",
            "MENTIONS": "Exact normalized alias match to a structured-source entity.",
            "HAS_TABLE": "Table artifact explicitly names its parent chunk.",
            "REFERENCES": "Explicit regulatory citation matched in source text.",
        },
        "do_not_claim": [
            "PARENT_OF is parser-derived structure, not an independently annotated ontology relation.",
            "MENTIONS indicates textual mention, not a causal or regulatory relationship.",
            "Structured supply-chain entities require separate source validation before predictive claims.",
            "REFERENCES does not imply DEPENDS_ON, COVERS, or causal influence.",
        ],
        "canonical_artifacts_replaced": False,
    }
    audit = {
        "hierarchy_fallbacks": hierarchy_fallbacks,
        "unresolved_table_parents": unresolved_tables,
    }
    write_json(output / "graph_manifest.json", report)
    write_json(output / "graph_audit.json", audit)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build staged regulatory evidence graph snapshot")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--extra-nodes", action="append", default=[], help="Additional validated JSONL node artifact; may be repeated")
    parser.add_argument("--extra-edges", action="append", default=[], help="Additional validated JSONL edge artifact; may be repeated")
    args = parser.parse_args()
    source = Path(args.source)
    output = Path(args.output)
    if output.exists():
        raise RuntimeError(f"refusing to overwrite existing graph snapshot: {output}")
    if not source.exists():
        raise FileNotFoundError(source)
    report = build_snapshot(
        source,
        output,
        extra_node_files=[Path(path) for path in args.extra_nodes],
        extra_edge_files=[Path(path) for path in args.extra_edges],
    )
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
