import json
import tempfile
import unittest
from pathlib import Path

from retrieval_ablation import (
    GroundTruthBuilder,
    dedupe_ranked_ids,
    weighted_reciprocal_rank_fusion,
)


class RankingFusionTests(unittest.TestCase):
    def test_dedupe_preserves_first_occurrence(self):
        self.assertEqual(dedupe_ranked_ids(["a", "b", "a"]), ["a", "b"])

    def test_graph_evidence_can_enter_top_five(self):
        fused = weighted_reciprocal_rank_fusion(
            [
                [f"dense-{i}" for i in range(1, 11)],
                ["graph-1", "graph-2"],
            ],
            weights=[1.0, 0.85],
        )
        self.assertIn("graph-1", fused[:5])


class GroundTruthPolicyTests(unittest.TestCase):
    def write_store(self, chunks_dir: Path):
        rows = [
            {
                "chunk_id": "ich_q7_canonical",
                "doc_id": "ich_q7",
                "content": "Active pharmaceutical ingredient testing requirements",
                "heading": "API testing",
                "summary": "",
            }
        ]
        (chunks_dir / "ich_q7_enriched.json").write_text(
            json.dumps(rows),
            encoding="utf-8",
        )

    def test_keyword_fallback_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chunks_dir = Path(temp_dir)
            self.write_store(chunks_dir)
            builder = GroundTruthBuilder(chunks_dir=chunks_dir)

            relevant = builder.build_for_query(
                {
                    "query": "What active pharmaceutical ingredient testing requirements apply?",
                    "relevant_docs": ["ICH Q7"],
                    "relevant_chunk_ids": ["missing_chunk"],
                }
            )

            self.assertEqual(relevant, set())
            self.assertEqual(builder.last_source, "none")

    def test_keyword_fallback_can_be_enabled_for_debugging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chunks_dir = Path(temp_dir)
            self.write_store(chunks_dir)
            builder = GroundTruthBuilder(
                chunks_dir=chunks_dir,
                allow_keyword_fallback=True,
            )

            relevant = builder.build_for_query(
                {
                    "query": "What active pharmaceutical ingredient testing requirements apply?",
                    "relevant_docs": ["ICH Q7"],
                    "relevant_chunk_ids": ["missing_chunk"],
                }
            )

            self.assertEqual(relevant, {"ich_q7_canonical"})
            self.assertEqual(builder.last_source, "keyword_fallback_debug_only")


if __name__ == "__main__":
    unittest.main()
