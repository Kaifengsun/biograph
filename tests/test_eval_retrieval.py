import json
import math
import tempfile
import unittest
from pathlib import Path

from eval_retrieval import (
    load_faiss_chunk_ids,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class RetrievalMetricTests(unittest.TestCase):
    def test_ndcg_penalizes_missed_relevant_chunks(self):
        score = ndcg_at_k(["a", "irrelevant"], ["a", "b"], 2)
        expected = 1.0 / (1.0 + 1.0 / math.log2(3))
        self.assertAlmostEqual(score, expected)
        self.assertLess(score, 1.0)

    def test_duplicate_retrieval_does_not_receive_duplicate_credit(self):
        retrieved = ["a", "a"]
        self.assertEqual(precision_at_k(retrieved, ["a"], 2), 0.5)
        self.assertEqual(recall_at_k(retrieved, ["a"], 2), 1.0)

    def test_mrr_uses_unique_chunk_ranks(self):
        self.assertEqual(mrr(["irrelevant", "irrelevant", "a"], ["a"]), 0.5)

    def test_loads_current_faiss_metadata_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "pharma_docs.faiss"
            meta_path = index_path.with_suffix(".meta.json")
            meta_path.write_text(
                json.dumps([{"chunk_id": "chunk-a"}, {"chunk_id": "chunk-b"}]),
                encoding="utf-8",
            )

            self.assertEqual(
                load_faiss_chunk_ids(str(index_path)),
                ["chunk-a", "chunk-b"],
            )

    def test_loads_legacy_id_list_as_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "pharma_docs.faiss"
            legacy_path = index_path.with_name("pharma_docs_ids.json")
            legacy_path.write_text(json.dumps(["chunk-a"]), encoding="utf-8")

            self.assertEqual(load_faiss_chunk_ids(str(index_path)), ["chunk-a"])


if __name__ == "__main__":
    unittest.main()
