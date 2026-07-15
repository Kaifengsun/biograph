import unittest

from freeze_three_path_evaluation_set import freeze_pack
from import_three_path_review_workbook import apply_decisions
from three_path_evaluation import evaluate_retrieval, validate_frozen_pack


def candidate_pack():
    return {
        "status": "candidate_pack_requires_human_review",
        "formal_metrics_ready": False,
        "queries": [
            {"annotation_id": "Q1", "query": "alpha", "query_slice": "single_clause", "gold_evidence_chunk_ids": [], "accepted_graph_path_node_ids": [], "review_status": "unreviewed", "eligible_for_formal_evaluation": False, "exclusion_reason": ""},
            {"annotation_id": "Q2", "query": "beta", "query_slice": "table", "gold_evidence_chunk_ids": [], "accepted_graph_path_node_ids": [], "review_status": "unreviewed", "eligible_for_formal_evaluation": False, "exclusion_reason": ""},
            {"annotation_id": "Q3", "query": "gamma", "query_slice": "cross_document", "gold_evidence_chunk_ids": [], "accepted_graph_path_node_ids": [], "review_status": "unreviewed", "eligible_for_formal_evaluation": False, "exclusion_reason": ""},
        ],
    }


class ThreePathEvaluationTests(unittest.TestCase):
    def test_confirmed_review_requires_frozen_source_and_graph_ids(self):
        result = apply_decisions(
            candidate_pack(),
            {"Q1": {"status": "Confirmed", "gold": "c1; c2", "path": "entity:a -> chunk:c1", "note": "direct source"}},
            {"c1", "c2", "c3"},
            {"entity:a", "chunk:c1"},
        )
        row = result["queries"][0]
        self.assertEqual(result["status"], "reviewer_workbook_applied_not_frozen")
        self.assertEqual(row["gold_evidence_chunk_ids"], ["c1", "c2"])
        self.assertEqual(row["accepted_graph_path_node_ids"], ["entity:a", "chunk:c1"])
        self.assertTrue(row["eligible_for_formal_evaluation"])

    def test_confirmed_review_rejects_unknown_chunk(self):
        with self.assertRaisesRegex(ValueError, "outside frozen corpus"):
            apply_decisions(
                candidate_pack(),
                {"Q1": {"status": "Confirmed", "gold": "missing", "path": "", "note": ""}},
                {"c1"},
                set(),
            )

    def test_freeze_requires_predeclared_balance(self):
        reviewed = candidate_pack()
        for row in reviewed["queries"]:
            row.update({"review_status": "reviewed", "eligible_for_formal_evaluation": True, "gold_evidence_chunk_ids": [f"{row['annotation_id']}_gold"]})
        frozen = freeze_pack(reviewed, min_total=3, min_table=1, min_cross_or_path=1)
        self.assertTrue(frozen["formal_metrics_ready"])
        self.assertEqual(len(frozen["queries"]), 3)
        self.assertEqual(validate_frozen_pack(frozen)[0]["annotation_id"], "Q1")

    def test_metrics_use_predeclared_rrf_and_path_subsequence(self):
        rows = [
            {"annotation_id": "Q1", "query": "alpha", "query_slice": "single_clause", "gold_evidence_chunk_ids": ["c2"], "accepted_graph_path_node_ids": []},
            {"annotation_id": "Q2", "query": "beta", "query_slice": "table", "gold_evidence_chunk_ids": ["c3"], "accepted_graph_path_node_ids": ["entity:b", "chunk:c3"]},
        ]
        retrieval_rows = [
            {"retrieval": {"query": "alpha", "bottom_up": [{"chunk_id": "c2"}], "top_down": {"evidence": [{"chunk_id": "c1"}]}, "graph_path": {"evidence": [{"chunk_id": "c4"}], "paths": []}}},
            {"retrieval": {"query": "beta", "bottom_up": [{"chunk_id": "c1"}], "top_down": {"evidence": [{"chunk_id": "c3"}]}, "graph_path": {"evidence": [{"chunk_id": "c3"}], "paths": [{"node_ids": ["entity:a", "entity:b", "chunk:c3"]}]}}},
        ]
        report = evaluate_retrieval(rows, retrieval_rows)
        self.assertEqual(report["aggregate"]["bottom_up"]["hit_at_1"], 0.5)
        self.assertEqual(report["aggregate"]["top_down"]["hit_at_1"], 0.5)
        self.assertEqual(report["aggregate"]["three_path_rrf"]["hit_at_3"], 1.0)
        self.assertEqual(report["graph_path_validation"]["success_at_5"], 1.0)

    def test_graph_path_validation_accepts_structured_paths(self):
        rows = [{
            "annotation_id": "Q1", "query": "alpha", "query_slice": "supply_chain_evidence_path",
            "gold_evidence_chunk_ids": ["c1"],
            "accepted_graph_path_node_ids": ["event:1", "ndc:1", "ingredient:1"],
        }]
        retrieval_rows = [{"retrieval": {
            "query": "alpha", "bottom_up": [{"chunk_id": "c1"}],
            "top_down": {"evidence": []},
            "graph_path": {"evidence": [], "paths": [
                {"node_ids": ["document:1", "chunk:1"]},
                {"node_ids": ["document:2", "chunk:2"]},
                {"node_ids": ["document:3", "chunk:3"]},
                {"node_ids": ["document:4", "chunk:4"]},
                {"node_ids": ["document:5", "chunk:5"]},
                {"node_ids": ["document:6", "chunk:6"]},
            ], "structured_paths": [{
                "node_ids": ["event:1", "ndc:1", "ingredient:1"],
            }]},
        }}]
        report = evaluate_retrieval(rows, retrieval_rows)
        self.assertEqual(report["graph_path_validation"]["success_at_5"], 1.0)

    def test_formal_validation_rejects_unfrozen_pack(self):
        with self.assertRaisesRegex(ValueError, "frozen"):
            validate_frozen_pack(candidate_pack())


if __name__ == "__main__":
    unittest.main()
