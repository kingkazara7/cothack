import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class P03P04ExtensionTests(unittest.TestCase):
    def test_p03_unique_candidate_and_evidence(self):
        subprocess.run([sys.executable, str(ROOT / "scripts/validate_p03_extension.py")], check=True, capture_output=True)

    def test_p04_repeated_observable_run(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_overthink_replay.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertGreater(result["P04-0"]["thinking_token_ratio"], 6)
        self.assertEqual(result["P04-0"]["attack_correct"], 3)
        self.assertGreater(result["P04-30"]["thinking_token_ratio"], 30)
        self.assertEqual(result["P04-30"]["attack_truncated"], 3)


if __name__ == "__main__":
    unittest.main()
