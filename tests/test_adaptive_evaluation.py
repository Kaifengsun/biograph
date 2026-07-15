import unittest

from activate_adaptive_heldout import query_content_hash
from evaluate_adaptive_text_first import adjust_holm, evidence_ids


class AdaptiveEvaluationTests(unittest.TestCase):
    def test_evidence_ids_deduplicates_in_rank_order(self):
        retrieval = {
            "top_down": {"evidence": [
                {"chunk_id": "c1"},
                {"chunk_id": "c1"},
                {"chunk_id": "c2"},
            ]}
        }
        self.assertEqual(evidence_ids(retrieval, "top_down"), ["c1", "c2"])

    def test_holm_adjustment_is_written_for_each_metric(self):
        comparisons = {
            "hit_at_5": {"p_value_raw": 0.01},
            "mrr": {"p_value_raw": 0.04},
            "ndcg_at_5": {"p_value_raw": 0.20},
        }
        adjust_holm(comparisons)
        self.assertEqual(comparisons["hit_at_5"]["p_value_holm"], 0.03)
        self.assertIn("significant_after_holm_0_05", comparisons["mrr"])

    def test_query_content_hash_ignores_dictionary_key_order(self):
        first = [{"annotation_id": "Q1", "query": "alpha"}]
        second = [{"query": "alpha", "annotation_id": "Q1"}]
        self.assertEqual(query_content_hash(first), query_content_hash(second))


if __name__ == "__main__":
    unittest.main()
