import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModelAccessAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(
            (ROOT / "results" / "model-access-audit-20261022.json").read_text()
        )

    def test_astra_has_calls_but_no_replay_payload(self):
        astra = self.audit["gpt_6_astra"]
        self.assertEqual(astra["status"], "actual_calls_observed")
        self.assertEqual(astra["schema"]["records"], 32)
        self.assertEqual(astra["schema"]["reasoning_item_count"], 0)
        self.assertFalse(astra["schema"]["signature_key_present"])
        self.assertFalse(astra["schema"]["encrypted_content_key_present"])
        self.assertFalse(astra["p01_replay_payload_available"])

    def test_anthropic_targets_are_not_run(self):
        for key in ("claude_fable_5_1", "claude_opus_5_5"):
            entry = self.audit[key]
            self.assertEqual(entry["status"], "not_run_missing_credential")
            self.assertFalse(entry["request_sent"])
            self.assertEqual(entry["errors"], ["missing_credential"])

    def test_source_log_hashes(self):
        astra = self.audit["gpt_6_astra"]
        for relative, expected in astra["source_log_sha256"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected)

    def test_public_web_evidence_hashes(self):
        spec = importlib.util.spec_from_file_location(
            "verify_web_evidence", ROOT / "scripts" / "verify_web_evidence.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        result = module.verify()
        self.assertEqual(result["verified"], 6)
