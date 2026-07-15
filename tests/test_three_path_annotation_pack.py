import unittest

from attach_three_path_retrieval_candidates import attach_candidates
from prepare_three_path_annotation_pack import candidate_row, merge_candidates


class ThreePathAnnotationPackTests(unittest.TestCase):
    def test_duplicate_query_merges_candidates_without_creating_gold_labels(self):
        first = candidate_row("a.json", "A", "What applies to X?", "single_clause", ["c1"])
        second = candidate_row("b.json", "B", "What applies to X?", "table", ["c2"])
        merged = merge_candidates([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["candidate_evidence_chunk_ids"], ["c1", "c2"])
        self.assertEqual(merged[0]["gold_evidence_chunk_ids"], [])
        self.assertFalse(merged[0]["eligible_for_formal_evaluation"])

    def test_excluded_row_preserves_reason(self):
        row = candidate_row("table.json", "TB", "No table", "table", exclusion_reason="no_viable")
        self.assertEqual(row["review_status"], "excluded")
        self.assertEqual(row["exclusion_reason"], "no_viable")

    def test_retrieval_attachment_adds_candidates_without_promoting_gold_labels(self):
        pack = {"queries": [candidate_row("a.json", "A", "What applies to X?", "single_clause")]}
        retrieval = [{"retrieval": {
            "query": "What applies to X?",
            "bottom_up": [{"chunk_id": "c1"}],
            "top_down": {"evidence": [{"chunk_id": "c2"}]},
            "graph_path": {"evidence": [{"chunk_id": "c3"}], "paths": [{"node_ids": ["a", "b"]}]},
        }}]
        result = attach_candidates(pack, retrieval, "pilot/per_query.json")
        row = result["queries"][0]
        self.assertEqual(row["candidate_evidence_chunk_ids"], ["c1", "c2", "c3"])
        self.assertEqual(row["gold_evidence_chunk_ids"], [])
        self.assertFalse(result["retrieval_candidate_attachment"]["formal_metrics_ready"])


if __name__ == "__main__":
    unittest.main()
