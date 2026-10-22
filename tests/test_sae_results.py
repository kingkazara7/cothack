import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("analyze_sae_results", ROOT / "scripts/analyze_sae_results.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

LATENT_SPEC = importlib.util.spec_from_file_location(
    "analyze_sae_latent_attack", ROOT / "scripts/analyze_sae_latent_attack.py"
)
LATENT_MODULE = importlib.util.module_from_spec(LATENT_SPEC)
assert LATENT_SPEC.loader is not None
sys.modules[LATENT_SPEC.name] = LATENT_MODULE
LATENT_SPEC.loader.exec_module(LATENT_MODULE)


class SAEAnswerParsing(unittest.TestCase):
    def test_final_answer_does_not_consume_next_answer_label(self):
        text = "### Final Answer:\n\nAnswer: D<|im_end|>"
        self.assertEqual(MODULE.final_answer(text), "D")

    def test_last_explicit_answer_wins(self):
        text = "Answer: B. After checking again, answer is A."
        self.assertEqual(MODULE.final_answer(text), "A")

    def test_target_repetition_requires_target_dominance(self):
        repeated = {
            "status": "ok",
            "repeated_suffix": True,
            "output_tokens": 10,
            "continuation": " A" * 10,
        }
        self.assertTrue(LATENT_MODULE.target_repetition(repeated))
        repeated["continuation"] = " A" * 8 + " D" * 2
        self.assertFalse(LATENT_MODULE.target_repetition(repeated))


if __name__ == "__main__":
    unittest.main()
