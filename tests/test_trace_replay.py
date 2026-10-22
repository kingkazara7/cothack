import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("trace_replay", ROOT / "scripts/reproduce_trace_replay.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TraceReplaySimulation(unittest.TestCase):
    def setUp(self):
        self.rows = MODULE.run_experiment()

    def attack_rows(self, mode):
        return [r for r in self.rows if r["case_id"].startswith("RTR-0") and r["mode"] == mode]

    def test_two_attack_cases_exist(self):
        self.assertEqual(len(self.attack_rows("vulnerable_global")), 2)
        self.assertEqual(len(self.attack_rows("context_bound")), 2)

    def test_unbound_blocks_replay_and_extract(self):
        self.assertTrue(all(r["simulated_extraction_event"] for r in self.attack_rows("vulnerable_global")))

    def test_context_binding_rejects_replay(self):
        rows = self.attack_rows("context_bound")
        self.assertTrue(all(not r["simulated_extraction_event"] for r in rows))
        self.assertTrue(all(r["result"]["reason"] == "ContextMismatch" for r in rows))

    def test_plaintext_is_not_in_serialized_block(self):
        rows = self.attack_rows("vulnerable_global") + self.attack_rows("context_bound")
        self.assertTrue(all(not r["plaintext_visible_in_block"] for r in rows))

    def test_authorized_continuation_still_works(self):
        rows = [r for r in self.rows if r["case_id"] == "RTR-C01"]
        self.assertEqual({r["result"]["status"] for r in rows}, {"accepted"})

    def test_tampering_is_rejected(self):
        rows = [r for r in self.rows if r["case_id"] == "RTR-C02"]
        self.assertEqual({r["result"]["status"] for r in rows}, {"rejected"})
        self.assertEqual({r["result"]["reason"] for r in rows}, {"InvalidBlock"})


if __name__ == "__main__":
    unittest.main()
