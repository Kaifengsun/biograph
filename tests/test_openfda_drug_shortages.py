import json
import tempfile
import unittest
from pathlib import Path

from collect_openfda_drug_shortages import collect_snapshot
from normalize_openfda_drug_shortages import normalize_snapshot


class OpenFdaDrugShortageTests(unittest.TestCase):
    def test_collector_writes_hashed_pages_and_normalizer_separates_event_type(self):
        pages = {
            "https://api.fda.gov/drug/shortages.json?limit=1": {"meta": {"results": {"total": 1}}, "results": [{}]},
            "https://api.fda.gov/drug/shortages.json?limit=100&skip=0": {
                "meta": {"results": {"total": 1}},
                "results": [{
                    "package_ndc": "12345-678-90", "generic_name": "Example Drug", "company_name": "Example Pharma",
                    "status": "Current", "initial_posting_date": "01/02/2025",
                    "openfda": {"substance_name": ["EXAMPLE DRUG"], "rxcui": ["123"]},
                }],
            },
        }
        def fetcher(url):
            payload = pages[url]
            body = json.dumps(payload).encode("utf-8")
            return payload, {}, body

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = root / "snapshot"
            normalized = root / "normalized"
            manifest = collect_snapshot(snapshot, fetcher=fetcher)
            report = normalize_snapshot(snapshot, normalized)
            self.assertEqual(manifest["downloaded_record_count"], 1)
            self.assertEqual(report["record_count"], 1)
            nodes = [json.loads(line) for line in (normalized / "fda_nodes.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertIn("FDA_DrugShortageEvent", {node["label"] for node in nodes})
            self.assertNotIn("RecallEvent", {node["label"] for node in nodes})

    def test_collector_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "existing"
            output.mkdir()
            with self.assertRaises(RuntimeError):
                collect_snapshot(output, fetcher=lambda _url: ({}, {}, b"{}"))
