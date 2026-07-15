import json
import tempfile
import unittest
from pathlib import Path

from pharma_doc_pipeline.config import PipelineSettings
from pharma_doc_pipeline.step_02_chunk import ChunkNode
from pharma_doc_pipeline.step_03_enrich import ContentEnricher
from run_full_local_enrichment_staging import (
    build_quality_report,
    collect_input_inventory,
    validate_preflight,
)


class EnrichmentContractTests(unittest.TestCase):
    def write_chunks(self, root: Path, doc_id: str, rows: list[dict]) -> None:
        (root / f"{doc_id}_chunks.json").write_text(
            json.dumps(rows),
            encoding="utf-8",
        )

    def test_preflight_accepts_matching_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_chunks(
                root,
                "ich_q7",
                [
                    {
                        "chunk_id": "ich_q7_C0001",
                        "content": "validated chunk",
                        "char_count": 15,
                    }
                ],
            )

            result = validate_preflight(
                root,
                expected={
                    "documents": 1,
                    "chunks": 1,
                    "max_chars_upper_bound": 20,
                    "excluded_doc_ids": ["arxiv_supply_chain"],
                },
            )

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["actual"]["documents"], 1)
            self.assertEqual(result["actual"]["chunks"], 1)

    def test_preflight_rejects_excluded_doc_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_chunks(
                root,
                "arxiv_supply_chain",
                [
                    {
                        "chunk_id": "bad_C0001",
                        "content": "wrong source",
                        "char_count": 12,
                    }
                ],
            )

            with self.assertRaisesRegex(RuntimeError, "excluded doc_id present"):
                validate_preflight(
                    root,
                    expected={
                        "documents": 1,
                        "chunks": 1,
                        "max_chars_upper_bound": 20,
                        "excluded_doc_ids": ["arxiv_supply_chain"],
                    },
                )

    def test_inventory_counts_table_summary_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_chunks(
                root,
                "ich_q7",
                [
                    {
                        "chunk_id": "ich_q7_C0001",
                        "content": "validated chunk",
                        "char_count": 15,
                    }
                ],
            )
            (root / "ich_q7_tables.json").write_text(
                json.dumps(
                    [
                        {"chunk_id": "ich_q7_C0001", "table": "| a | b |"},
                        {
                            "chunk_id": "ich_q7_C0001",
                            "table": "| c | d |",
                            "table_summary": "summary",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            inventory = collect_input_inventory(root)

            self.assertEqual(inventory["tables"]["rows"], 2)
            self.assertEqual(inventory["tables"]["rows_with_summary"], 1)

    def test_enrich_chunks_writes_meta_without_llm_calls(self):
        settings = PipelineSettings()
        settings.chunking.enable_hyde = False
        settings.chunking.summary_trigger_chars = 9999
        settings.chunking.summary_trigger_lines = 9999
        enricher = ContentEnricher(settings=settings)
        chunk = ChunkNode(
            chunk_id="ich_q7_C0001",
            doc_id="ich_q7",
            heading="API controls",
            content="Manufacturers document controls for APIs.",
            search_text="Manufacturers document controls for APIs.",
            char_count=43,
            line_count=1,
        )

        rows = enricher.enrich_chunks([chunk])

        meta = rows[0]["enrichment_meta"]
        self.assertFalse(meta["summary_eligible"])
        self.assertFalse(meta["hyde_enabled"])
        self.assertEqual(meta["hyde_questions_generated"], 0)
        self.assertEqual(enricher.get_runtime_quality_report()["new_llm_calls"], 0)

    def test_quality_report_counts_enrichment_meta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_chunks(
                root,
                "ich_q7",
                [
                    {
                        "chunk_id": "ich_q7_C0001",
                        "content": "validated chunk",
                        "char_count": 600,
                    }
                ],
            )
            (root / "ich_q7_enriched.json").write_text(
                json.dumps(
                    [
                        {
                            "chunk_id": "ich_q7_C0001",
                            "content": "validated chunk",
                            "char_count": 600,
                            "summary": "summary",
                            "hyde_questions": ["question?"],
                            "enrichment_meta": {
                                "summary_eligible": True,
                                "hyde_eligible": True,
                                "hyde_strategy": "C1",
                                "source_grounding": {
                                    "unsupported_named_reference_questions_filtered": 2
                                },
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            report = build_quality_report(root)
            counters = report["artifact_counters"]

            self.assertEqual(report["status"], "complete_enriched_artifacts")
            self.assertEqual(counters["chunks_with_enrichment_meta"], 1)
            self.assertEqual(counters["hyde_c1_chunks"], 1)
            self.assertEqual(
                counters["unsupported_named_reference_questions_filtered"],
                2,
            )


if __name__ == "__main__":
    unittest.main()
