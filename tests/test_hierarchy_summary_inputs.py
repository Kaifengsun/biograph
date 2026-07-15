import json
import tempfile
import unittest
from pathlib import Path

from prepare_hierarchy_summary_inputs import build_inputs


class HierarchySummaryInputTests(unittest.TestCase):
    def write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_document_summary_depends_on_section_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph"
            source = root / "source"
            output = root / "output"
            graph.mkdir()
            source.mkdir()
            self.write_jsonl(graph / "nodes.jsonl", [
                {
                    "id": "regdoc:d", "label": "RegulatoryDocument", "name": "Document D",
                    "properties": {"doc_id": "d"},
                },
                {
                    "id": "chunk:d_1", "label": "DocChunk", "name": "Section A",
                    "properties": {"chunk_id": "d_1", "doc_id": "d", "heading": "Section A", "level": 1, "summary": ""},
                },
                {
                    "id": "chunk:d_2", "label": "DocChunk", "name": "Clause A.1",
                    "properties": {"chunk_id": "d_2", "doc_id": "d", "heading": "Clause A.1", "level": 2, "summary": "Leaf summary."},
                },
            ])
            self.write_jsonl(graph / "edges.jsonl", [
                {"source": "regdoc:d", "target": "chunk:d_1", "relation": "CONTAINS", "properties": {}},
                {"source": "chunk:d_1", "target": "chunk:d_2", "relation": "PARENT_OF", "properties": {}},
            ])
            (source / "d_enriched.json").write_text(
                json.dumps([
                    {"chunk_id": "d_1", "content": "Section header."},
                    {"chunk_id": "d_2", "content": "Clause content."},
                ]),
                encoding="utf-8",
            )

            report = build_inputs(graph, source, output)
            rows = [
                json.loads(line)
                for line in (output / "hierarchy_summary_inputs.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            section = next(row for row in rows if row["summary_id"] == "section:d_1")
            document = next(row for row in rows if row["summary_id"] == "document:d")

            self.assertEqual(report["expected_llm_calls"], 2)
            self.assertEqual(section["source_units"][1]["source_text"], "Leaf summary.")
            self.assertEqual(document["source_units"][0]["depends_on"], "section:d_1")


if __name__ == "__main__":
    unittest.main()
