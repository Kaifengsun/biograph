import unittest

from attach_llm_assisted_reviews import attach_reviews
from llm_assisted_annotation_review import parse_review


class LlmAssistedAnnotationReviewTests(unittest.TestCase):
    def test_parser_discards_unprovided_chunk_ids(self):
        review = parse_review(
            '{"direct_support_chunk_ids":["valid","invented"],"insufficient_evidence":false,"rationale":"supported"}',
            ["valid"],
        )
        self.assertEqual(review["direct_support_chunk_ids"], ["valid"])
        self.assertTrue(review["output_valid"])

    def test_parser_marks_invalid_json_as_non_supporting(self):
        review = parse_review("not json", ["valid"])
        self.assertEqual(review["direct_support_chunk_ids"], [])
        self.assertTrue(review["insufficient_evidence"])
        self.assertFalse(review["output_valid"])

    def test_parser_accepts_fenced_json(self):
        review = parse_review(
            '```json\n{"direct_support_chunk_ids":["valid"],"insufficient_evidence":false,"rationale":"supported"}\n```',
            ["valid"],
        )
        self.assertEqual(review["direct_support_chunk_ids"], ["valid"])
        self.assertTrue(review["output_valid"])

    def test_attachment_preserves_non_formal_status(self):
        pack = {"queries": [{"annotation_id": "Q1", "eligible_for_formal_evaluation": False}]}
        reviews = [{"annotation_id": "Q1", "model": "model", "prompt_version": "v1", "review": {"insufficient_evidence": False}}]
        result = attach_reviews(pack, reviews, "reviews.jsonl")
        self.assertIn("llm_assisted_review", result["queries"][0])
        self.assertFalse(result["llm_assisted_review_attachment"]["formal_gold_labels_created"])


if __name__ == "__main__":
    unittest.main()
