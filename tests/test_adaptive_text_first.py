import unittest

from adaptive_text_first import (
    AdaptiveParameters,
    adaptive_rank,
    explicit_document_ids,
    graph_gate,
    is_table_evidence,
    is_table_query,
)


def item(chunk_id, doc_id="doc", heading="Section", content="source text"):
    return {"chunk_id": chunk_id, "doc_id": doc_id, "heading": heading, "content": content}


class AdaptiveTextFirstTests(unittest.TestCase):
    def test_explicit_document_alias_matches_annex(self):
        rows = [item("c1", "ema_gmp_annex_11"), item("c2", "ich_q9")]
        self.assertEqual(explicit_document_ids("What does EMA GMP Annex 11 require?", rows), {"ema_gmp_annex_11"})

    def test_table_intent_and_source_marker(self):
        self.assertTrue(is_table_query("Which table gives the PDE threshold?"))
        self.assertTrue(is_table_evidence(item("c1", content="[表: Solvent, PDE]")))
        self.assertFalse(is_table_evidence(item("c2")))

    def test_graph_gate_abstains_without_anchor(self):
        enabled, reason = graph_gate({"graph_path": {"anchors": [], "evidence": []}}, set())
        self.assertFalse(enabled)
        self.assertEqual(reason, "no_qualified_graph_anchor")

    def test_graph_gate_accepts_structured_record(self):
        enabled, reason = graph_gate({"graph_path": {"structured_evidence": [{"node_id": "event:1"}]}}, set())
        self.assertTrue(enabled)
        self.assertEqual(reason, "direct_structured_record")

    def test_disabled_graph_does_not_leak_zero_score_chunks(self):
        retrieval = {
            "query": "plain text question",
            "bottom_up": [item("text-1")],
            "top_down": {"selected_documents": ["doc"], "evidence": []},
            "graph_path": {"anchors": [], "evidence": [item("graph-only")]},
        }
        result = adaptive_rank(retrieval, AdaptiveParameters(graph_weight=1.0))
        self.assertEqual(result["ranking"], ["text-1"])

    def test_topic_graph_requires_text_route_agreement(self):
        retrieval = {
            "top_down": {"selected_documents": ["ema_gmp_annex_11"]},
            "graph_path": {
                "anchors": [{"label": "RegulatoryTopic"}],
                "reachable_documents": ["ema_gmp_annex_11"],
                "evidence": [item("c1", "ema_gmp_annex_11")],
            },
        }
        self.assertEqual(graph_gate(retrieval, set()), (True, "topic_path_agrees_with_text_route"))

    def test_text_route_retention_survives_large_graph_weight(self):
        retrieval = {
            "query": "Carboplatin shortage",
            "bottom_up": [item("bottom-1")],
            "top_down": {"selected_documents": ["doc"], "evidence": [item("top-1")]},
            "graph_path": {
                "structured_evidence": [{"node_id": "event:1"}],
                "evidence": [item(f"graph-{index}") for index in range(1, 8)],
            },
        }
        result = adaptive_rank(
            retrieval,
            AdaptiveParameters(graph_weight=20.0, retain_text_top_n=1),
            top_k=5,
        )
        self.assertIn("bottom-1", result["top_k"])
        self.assertIn("top-1", result["top_k"])
        self.assertTrue(result["audit"]["retention_actions"])

    def test_fixed_inputs_are_deterministic(self):
        retrieval = {
            "query": "What does ICH Q9 require?",
            "bottom_up": [item("c1", "ich_q9"), item("c2", "ich_q10")],
            "top_down": {"selected_documents": ["ich_q9"], "evidence": [item("c2", "ich_q10"), item("c1", "ich_q9")]},
            "graph_path": {"anchors": [], "evidence": []},
        }
        self.assertEqual(adaptive_rank(retrieval), adaptive_rank(retrieval))


if __name__ == "__main__":
    unittest.main()
