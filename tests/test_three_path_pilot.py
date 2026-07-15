import json
import tempfile
import unittest
from pathlib import Path

from run_three_path_pilot import read_queries


class ThreePathPilotSafetyTests(unittest.TestCase):
    def test_prohibited_frozen_bundle_cannot_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.json"
            path.write_text(json.dumps({
                "retrieval_execution_prohibited": True,
                "queries": [{"annotation_id": "Q1", "query": "alpha"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "execution remains prohibited"):
                read_queries(path)

    def test_active_bundle_returns_annotation_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.json"
            path.write_text(json.dumps({
                "retrieval_execution_prohibited": False,
                "queries": [{"annotation_id": "Q1", "query": "alpha"}],
            }), encoding="utf-8")
            self.assertEqual(read_queries(path)[0]["annotation_id"], "Q1")


if __name__ == "__main__":
    unittest.main()
