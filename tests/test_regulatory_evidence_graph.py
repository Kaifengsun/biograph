import unittest
import tempfile
from pathlib import Path
import json

from build_regulatory_evidence_graph import (
    EntityAlias,
    explicit_references,
    exact_entity_mentions,
    hierarchy_edges,
    next_edges,
    reference_catalog,
)


class RegulatoryEvidenceGraphTests(unittest.TestCase):
    def test_hierarchy_reconstructs_one_parent_per_nested_chunk(self):
        rows = [
            {"chunk_id": "d_1", "doc_id": "d", "heading": "A", "level": 1},
            {"chunk_id": "d_2", "doc_id": "d", "heading": "A.1", "level": 2},
            {"chunk_id": "d_3", "doc_id": "d", "heading": "A.1.a", "level": 3},
            {"chunk_id": "d_4", "doc_id": "d", "heading": "A.2", "level": 2},
            {"chunk_id": "d_5", "doc_id": "d", "heading": "B", "level": 1},
        ]

        edges, parents, fallbacks = hierarchy_edges(rows, "d_enriched.json")
        parent_edges = {
            (edge["source"], edge["target"])
            for edge in edges
            if edge["relation"] == "PARENT_OF"
        }

        self.assertEqual(parents, {"d_2": "d_1", "d_3": "d_2", "d_4": "d_1"})
        self.assertIn(("chunk:d_1", "chunk:d_2"), parent_edges)
        self.assertIn(("chunk:d_2", "chunk:d_3"), parent_edges)
        self.assertEqual(fallbacks, [])

    def test_next_edges_exclude_unknown_target(self):
        rows = [
            {"chunk_id": "d_1", "next_chunk_id": "d_2"},
            {"chunk_id": "d_2", "next_chunk_id": "missing"},
        ]
        edges = next_edges(rows, "d_enriched.json", {"d_1", "d_2"})
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["target"], "chunk:d_2")

    def test_exact_alias_linker_requires_whole_normalized_alias(self):
        aliases = [EntityAlias("MFG_acme", "Manufacturer", "Acme Pharma", "acme pharma")]
        rows = [
            {"chunk_id": "d_1", "heading": "Supplier", "content": "Acme Pharma must qualify systems."},
            {"chunk_id": "d_2", "heading": "Other", "content": "Acmepharma is not an exact alias."},
        ]
        edges = exact_entity_mentions(rows, "d_enriched.json", aliases)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["source"], "chunk:d_1")

    def test_explicit_reference_links_known_document(self):
        documents = {
            "ich_q7": [{"doc_id": "ich_q7", "heading": "Q7"}],
            "ich_q9": [{"doc_id": "ich_q9", "heading": "Q9"}],
        }
        catalog = reference_catalog(documents)
        rows = [{
            "chunk_id": "ich_q7_C1",
            "doc_id": "ich_q7",
            "heading": "Quality risk management",
            "content": "See ICH Q9 for risk-management principles.",
        }]
        edges, unresolved = explicit_references(rows, "ich_q7_enriched.json", catalog)
        self.assertEqual(len(unresolved), 0)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["target"], "regdoc:ich_q9")
        self.assertEqual(edges[0]["relation"], "REFERENCES")

    def test_catalog_resolves_unique_unversioned_ich_alias_only(self):
        catalog = reference_catalog({
            "ich_q2r2": [{"doc_id": "ich_q2r2", "heading": "Q2"}],
            "ich_q1a": [{"doc_id": "ich_q1a", "heading": "Q1A"}],
            "ich_q1b": [{"doc_id": "ich_q1b", "heading": "Q1B"}],
        })
        self.assertEqual(catalog["ICH Q2"], "ich_q2r2")
        self.assertNotIn("ICH Q1", catalog)

    def test_graph_extension_rejects_dangling_attachment_edge(self):
        from extend_graph_snapshot import extend_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "base"
            output = root / "output"
            base.mkdir()
            (base / "nodes.jsonl").write_text(json.dumps({"id": "n:1", "label": "Node", "name": "one", "properties": {}}) + "\n", encoding="utf-8")
            (base / "edges.jsonl").write_text("", encoding="utf-8")
            nodes = root / "nodes.jsonl"
            edges = root / "edges.jsonl"
            nodes.write_text("", encoding="utf-8")
            edges.write_text(json.dumps({"source": "n:1", "target": "n:missing", "relation": "TEST", "properties": {}}) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                extend_snapshot(base, output, [nodes], [edges])

    def test_graph_extension_repairs_known_drug_class_endpoint(self):
        from extend_graph_snapshot import extend_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "base"
            output = root / "output"
            empty_nodes = root / "extra_nodes.jsonl"
            empty_edges = root / "extra_edges.jsonl"
            base.mkdir()
            (base / "nodes.jsonl").write_text(json.dumps({"id": "entity:TA_antibiotic", "label": "TherapeuticArea", "name": "area", "properties": {}}) + "\n", encoding="utf-8")
            (base / "edges.jsonl").write_text(json.dumps({"source": "entity:antibiotic", "target": "entity:TA_antibiotic", "relation": "BELONGS_TO_AREA", "properties": {}}) + "\n", encoding="utf-8")
            empty_nodes.write_text("", encoding="utf-8")
            empty_edges.write_text("", encoding="utf-8")
            report = extend_snapshot(base, output, [empty_nodes], [empty_edges])
            self.assertEqual(report["integrity_repairs"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
