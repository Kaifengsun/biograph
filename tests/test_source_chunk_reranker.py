import unittest

from source_chunk_reranker import (
    RerankParameters,
    SelectiveParameters,
    is_table_chunk,
    ordered_union,
    rerank_source_chunks,
    selective_rerank_source_chunks,
    route_query,
)


class SourceChunkRerankerTests(unittest.TestCase):
    def setUp(self):
        self.records = {
            "c1": {"chunk_id": "c1", "doc_id": "ich_q9", "heading": "Risk", "content": "risk text"},
            "c2": {"chunk_id": "c2", "doc_id": "ich_q2r2", "heading": "Table 1", "content": "values"},
            "c3": {"chunk_id": "c3", "doc_id": "fda_cgmp_guidance", "heading": "Design", "content": "manufacturing"},
        }

    def test_route_precedence_and_independent_graph_gate(self):
        route = route_query("Which table in ICH Q9 concerns a drug shortage?", {"ich_q9"})
        self.assertEqual(route["text_route"], "table")
        self.assertTrue(route["graph_enabled"])
        self.assertEqual(route["explicit_document_ids"], ["ich_q9"])

    def test_ordered_union_deduplicates_without_reordering(self):
        self.assertEqual(ordered_union(["c1", "c2"], ["c2", "c3"]), ["c1", "c2", "c3"])

    def test_table_membership_is_structured_or_textual(self):
        self.assertTrue(is_table_chunk(self.records["c1"], {"c1"}))
        self.assertTrue(is_table_chunk(self.records["c2"], set()))
        self.assertFalse(is_table_chunk(self.records["c3"], set()))

    def test_unknown_sidecar_or_chunk_is_rejected(self):
        with self.assertRaises(ValueError):
            rerank_source_chunks(
                "risk", ["c1"], ["sidecar"], self.records, [], set(), RerankParameters()
            )

    def test_score_audit_sums_and_lexical_top1_is_preserved(self):
        result = rerank_source_chunks(
            "What does ICH Q9 require?",
            ["c1", "c2"],
            ["c2", "c1"],
            self.records,
            ["ich_q2r2", "ich_q9"],
            {"c2"},
            RerankParameters(lexical_bm25_weight=2.0, explicit_document_weight=1.0),
        )
        self.assertEqual(result["route"]["text_route"], "lexical")
        self.assertEqual(result["ranking"][0], "c1")
        for row in result["score_audit"]:
            self.assertAlmostEqual(row["score"], sum(row["contributions"].values()))

    def test_selective_gate_returns_bm25_unchanged_when_disabled(self):
        result = selective_rerank_source_chunks(
            "How should quality risk be managed?", ["c1", "c2"], ["c2", "c1"],
            self.records, [], {"c2"}, SelectiveParameters(table_support_depth=1, table_support_threshold=2),
        )
        self.assertFalse(result["table_gate"]["enabled"])
        self.assertEqual(result["ranking"], ["c1", "c2"])

    def test_selective_gate_enables_source_only_fusion_with_support(self):
        result = selective_rerank_source_chunks(
            "How should quality risk be managed?", ["c1", "c2", "c3"], ["c2", "c1", "c3"],
            self.records, [], {"c1", "c2"}, SelectiveParameters(table_support_depth=2, table_support_threshold=2),
        )
        self.assertTrue(result["table_gate"]["enabled"])
        self.assertEqual(set(result["ranking"]), {"c1", "c2", "c3"})


if __name__ == "__main__":
    unittest.main()
