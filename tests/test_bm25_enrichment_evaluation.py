import unittest

from evaluate_bm25_enrichment_ablation import BM25Index, dedupe_source_ranking, metric_row, rrf_rank, tokenize


class BM25EnrichmentEvaluationTests(unittest.TestCase):
    def test_tokenizer_is_lowercase_alphanumeric(self):
        self.assertEqual(tokenize("ICH Q14: Risk-based/ATP"), ["ich", "q14", "risk", "based", "atp"])

    def test_bm25_ranks_matching_source_first(self):
        records = [
            {"chunk_id": "a", "parents_context": "", "heading": "Viral clearance", "content": "model virus selection"},
            {"chunk_id": "b", "parents_context": "", "heading": "Stability", "content": "storage conditions"},
        ]
        self.assertEqual(BM25Index.build(records).rank("model virus", 2)[0], "a")

    def test_sidecar_vectors_map_back_to_unique_source_chunks(self):
        metadata = [{"chunk_id": "a"}, {"chunk_id": "a"}, {"chunk_id": "b"}]
        self.assertEqual(dedupe_source_ranking([0, 1, 2], metadata), ["a", "b"])

    def test_rrf_uses_equal_channels_and_deduplicates(self):
        ranking = rrf_rank([["a", "b"], ["b", "c"]], k=60)
        self.assertEqual(ranking[0], "b")
        self.assertEqual(len(ranking), 3)

    def test_metrics_handle_multiple_gold_chunks(self):
        row = metric_row(["x", "a", "b"], {"a", "b"})
        self.assertEqual(row["hit_at_1"], 0.0)
        self.assertEqual(row["hit_at_3"], 1.0)
        self.assertEqual(row["mrr"], 0.5)
        self.assertGreater(row["ndcg_at_5"], 0.0)


if __name__ == "__main__":
    unittest.main()
