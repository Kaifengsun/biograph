import json
import tempfile
import unittest
from pathlib import Path

from three_path_retrieval import ThreePathSnapshotRetriever


class ThreePathSnapshotRetrieverTests(unittest.TestCase):
    def make_retriever(self):
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        graph = root / "graph"
        corpus = root / "corpus"
        graph.mkdir()
        corpus.mkdir()
        nodes = [
            {"id": "regdoc:doc_a", "label": "RegulatoryDocument", "name": "ICH Q12", "properties": {"doc_id": "doc_a"}},
            {"id": "chunk:root", "label": "DocChunk", "name": "Lifecycle", "properties": {"chunk_id": "root"}},
            {"id": "chunk:child", "label": "DocChunk", "name": "Change management", "properties": {"chunk_id": "child"}},
            {"id": "entity:carboplatin", "label": "Drug", "name": "Carboplatin", "properties": {}},
            {"id": "fda_shortage:carboplatin", "label": "FDA_DrugShortageEvent", "name": "Carboplatin Injection", "properties": {"company_name": "Accord Healthcare", "package_ndc": "16729-295-34", "availability": "Unavailable", "shortage_reason": "GMP compliance"}},
            {"id": "fda_ndc:16729-295-34", "label": "FDANDCProduct", "name": "16729-295-34", "properties": {}},
            {"id": "fda_ingredient:carboplatin", "label": "FDAActiveIngredient", "name": "Carboplatin", "properties": {}},
        ]
        edges = [
            {"source": "regdoc:doc_a", "target": "chunk:root", "relation": "CONTAINS", "properties": {}},
            {"source": "chunk:root", "target": "chunk:child", "relation": "PARENT_OF", "properties": {}},
            {"source": "chunk:child", "target": "entity:carboplatin", "relation": "MENTIONS", "properties": {"provenance": {"source_file": "source"}}},
            {"source": "fda_shortage:carboplatin", "target": "fda_ndc:16729-295-34", "relation": "AFFECTS_NDC_PRODUCT", "properties": {}},
            {"source": "fda_ndc:16729-295-34", "target": "fda_ingredient:carboplatin", "relation": "HAS_ACTIVE_INGREDIENT", "properties": {}},
        ]
        (graph / "nodes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in nodes), encoding="utf-8")
        (graph / "edges.jsonl").write_text("".join(json.dumps(row) + "\n" for row in edges), encoding="utf-8")
        chunks = [
            {"chunk_id": "root", "doc_id": "doc_a", "heading": "Lifecycle", "content": "Lifecycle text."},
            {"chunk_id": "child", "doc_id": "doc_a", "heading": "Change management", "content": "Carboplatin evidence."},
        ]
        (corpus / "doc_a_enriched.json").write_text(json.dumps(chunks), encoding="utf-8")
        retriever = ThreePathSnapshotRetriever(graph_dir=graph, corpus_dir=corpus, index_root=root / "indexes")
        return temp_dir, retriever

    def test_bottom_up_returns_source_chunk_evidence(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            evidence = retriever.bottom_up_from_rankings([
                {"chunk_id": "child", "vector_score": 0.9, "vector_rank": 1, "type": "summary"},
            ])
            self.assertEqual(evidence[0].chunk_id, "child")
            self.assertEqual(evidence[0].content, "Carboplatin evidence.")

    def test_top_down_uses_selected_document_and_real_tree_edge(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.top_down_from_rankings(
                [{"doc_id": "doc_a", "chunk_id": "root", "vector_score": 0.8, "vector_rank": 1}],
                [{"doc_id": "doc_a", "chunk_id": "root", "vector_score": 0.7, "vector_rank": 1}],
            )
            self.assertEqual(result["selected_documents"], ["doc_a"])
            self.assertIn("child", {item.chunk_id for item in result["evidence"]})

    def test_graph_paths_are_existing_acyclic_edges(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search("What applies to Carboplatin?", max_depth=3)
            self.assertFalse(result["abstained"])
            path = result["paths"][0]
            self.assertEqual(path["node_ids"][-1], "chunk:child")
            self.assertEqual(len(path["node_ids"]), len(set(path["node_ids"])))
            self.assertEqual(path["edges"][0]["relation"], "MENTIONS")

    def test_graph_path_abstains_without_anchor(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search("unrelated unknown query")
            self.assertTrue(result["abstained"])

    def test_graph_path_reports_expansion_budget(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search("Carboplatin", max_state_expansions=1)
            self.assertEqual(result["search_budget"]["states_expanded"], 1)
            self.assertTrue(result["search_budget"]["truncated"])

    def test_document_anchor_prefers_its_own_contained_chunk(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search("ICH Q12", max_depth=2)
            self.assertEqual(result["paths"][0]["node_ids"], ["regdoc:doc_a", "chunk:root"])

    def test_graph_backfill_reranks_source_chunks_within_reachable_document(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search(
                "ICH Q12",
                max_depth=2,
                source_rows=[{"doc_id": "doc_a", "chunk_id": "child", "vector_score": 0.91, "vector_rank": 1}],
            )
            self.assertEqual(result["evidence"][0].chunk_id, "child")
            self.assertEqual(result["evidence"][0].route, "graph_path_r2_backfill")

    def test_graph_path_records_anchor_path_budget(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search("Carboplatin", max_paths_per_anchor=1)
            self.assertEqual(result["search_budget"]["max_paths_per_anchor"], 1)

    def test_shortage_event_is_exposed_as_structured_not_chunk_evidence(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            result = retriever.graph_path_search("Accord Carboplatin NDC 16729-295-34")
            structured = result["structured_evidence"]
            self.assertEqual(structured[0]["node_id"], "fda_shortage:carboplatin")
            self.assertEqual(structured[0]["record"]["availability"], "Unavailable")
            self.assertEqual(structured[0]["path"]["node_ids"], [
                "fda_shortage:carboplatin", "fda_ndc:16729-295-34", "fda_ingredient:carboplatin",
            ])

    def test_generic_chunk_heading_is_not_an_anchor(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            self.assertEqual(retriever.entity_anchors("What system is required?"), [])

    def test_document_anchor_requires_complete_alias_not_prefix(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            self.assertEqual(retriever.entity_anchors("Does ICH Q1 apply?"), [])
            self.assertIn("regdoc:doc_a", retriever.entity_anchors("Does ICH Q12 apply?"))

    def test_custom_query_embedder_is_accepted_without_loading_legacy_retriever(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            retriever._embed_queries = lambda _queries: __import__("numpy").ones((1, 2), dtype="float32")
            vector = retriever.encode_query("Carboplatin")
            self.assertEqual(vector.shape, (1, 2))

    def test_batch_query_embedding_preserves_query_rows(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            retriever._embed_queries = lambda queries: __import__("numpy").ones((len(queries), 2), dtype="float32")
            vectors = retriever.encode_queries(["Carboplatin", "ICH Q12"])
            self.assertEqual(vectors.shape, (2, 2))

    def test_retrieve_all_encodes_query_once(self):
        temp_dir, retriever = self.make_retriever()
        with temp_dir:
            calls = []
            retriever.encode_query = lambda query: calls.append(query) or __import__("numpy").ones((1, 2), dtype="float32")
            retriever.rank_variant = lambda variant, query, k, query_vector=None: [
                {"doc_id": "doc_a", "chunk_id": "child", "vector_score": 0.8, "vector_rank": 1, "type": "summary"}
            ]
            retriever.retrieve_all("Carboplatin", max_depth=2)
            self.assertEqual(calls, ["Carboplatin"])


if __name__ == "__main__":
    unittest.main()
