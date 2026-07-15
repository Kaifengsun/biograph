import unittest

from pharma_doc_pipeline.step_02_chunk import ChunkNode
from pharma_doc_pipeline.step_03_enrich import ContentEnricher


class EnrichmentGroundingTests(unittest.TestCase):
    def setUp(self):
        self.enricher = object.__new__(ContentEnricher)
        self.enricher._doc_source_map = {
            "ich_q6b": {
                "title": "ICH Q6B Specifications for Biotechnological/Biological Products",
                "authority": "ICH",
            },
            "fda_cgmp_guidance": {
                "title": "FDA cGMP Guidance",
                "authority": "FDA",
            },
        }

    def test_rejects_unsupported_ich_guideline_number(self):
        chunk = ChunkNode(
            doc_id="ich_q6b",
            heading="Degradation Products",
            content="Degradation products may result from storage conditions.",
        )

        self.assertFalse(
            self.enricher._has_supported_named_references(
                "How does ICH Q7 stability testing affect manufacturers?",
                chunk,
            )
        )

    def test_accepts_ich_guideline_named_in_excerpt(self):
        chunk = ChunkNode(
            doc_id="ich_q6b",
            heading="Cell banks",
            content="See ICH Guideline Q5D for a complete discussion of cell banking.",
        )

        self.assertTrue(
            self.enricher._has_supported_named_references(
                "What storage controls are required by ICH Guideline Q5D?",
                chunk,
            )
        )

    def test_rejects_unsupported_authority(self):
        chunk = ChunkNode(
            doc_id="fda_cgmp_guidance",
            heading="Packaging controls",
            content="Manufacturers should document packaging controls.",
        )

        self.assertFalse(
            self.enricher._has_supported_named_references(
                "What WHO packaging controls must manufacturers document?",
                chunk,
            )
        )

    def test_table_cache_key_is_content_stable(self):
        first = self.enricher._table_cache_key("| a | b |")
        second = self.enricher._table_cache_key("| a | b |")
        changed = self.enricher._table_cache_key("| a | c |")

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
