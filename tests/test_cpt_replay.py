import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_cpt_replay", ROOT / "scripts/validate_cpt_replay.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CPTReplayValidation(unittest.TestCase):
    def test_has_two_valid_deepseek_cases(self):
        result = MODULE.validate()
        self.assertEqual(result["valid_cases"], 2)
        self.assertEqual(result["targeted_successes"], 0)
        self.assertEqual(result["targeted_success_rate"], 0)
