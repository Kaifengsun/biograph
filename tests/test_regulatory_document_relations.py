import tempfile
import unittest
from pathlib import Path

from extract_regulatory_document_relations import RelationRule, extract_rules


class RegulatoryDocumentRelationTests(unittest.TestCase):
    def test_explicit_complement_relation_captures_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "ich_q14").mkdir()
            source = root / "ich_q14" / "ich_q14.md"
            source.write_text("This guideline complements ICH Q2 Validation of Analytical Procedures.", encoding="utf-8")
            rules = [RelationRule("TEST-001", "ich_q14", "COMPLEMENTS", "doc", "ich_q2r2", r"complements\s+ICH\s+Q2")]
            _nodes, edges, audit = extract_rules(rules, {"ich_q14", "ich_q2r2"}, root)
            self.assertEqual(audit[0]["status"], "accepted")
            self.assertEqual(edges[0]["target"], "regdoc:ich_q2r2")
            self.assertIn("evidence_text", edges[0]["properties"])

    def test_missing_or_bibliography_only_text_does_not_emit_relation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "ich_q14").mkdir()
            (root / "ich_q14" / "ich_q14.md").write_text("References: ICH Q2.", encoding="utf-8")
            rules = [RelationRule("TEST-002", "ich_q14", "COMPLEMENTS", "doc", "ich_q2r2", r"This\s+guideline\s+complements\s+ICH\s+Q2")]
            _nodes, edges, audit = extract_rules(rules, {"ich_q14", "ich_q2r2"}, root)
            self.assertEqual(edges, [])
            self.assertEqual(audit[0]["status"], "rejected_evidence_not_found")

    def test_external_reference_has_deterministic_node(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "fda_cgmp_guidance").mkdir()
            (root / "fda_cgmp_guidance" / "fda_cgmp_guidance.md").write_text("Readers should refer to parts 210 and 211 to ensure full compliance.", encoding="utf-8")
            rules = [RelationRule("TEST-003", "fda_cgmp_guidance", "REQUIRES_COMPLIANCE_WITH", "external", "21 CFR Parts 210 and 211", r"refer\s+to\s+parts\s+210\s+and\s+211\s+to\s+ensure\s+full\s+compliance")]
            nodes, edges, _audit = extract_rules(rules, {"fda_cgmp_guidance"}, root)
            self.assertEqual(nodes[0]["label"], "RegulatoryReference")
            self.assertEqual(edges[0]["target"], nodes[0]["id"])
