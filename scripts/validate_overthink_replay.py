#!/usr/bin/env python3
"""Validate the observable Qwen3-8B OverThink replay and recompute ratios."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", default="logs/p04/p04-qwen3-8b.jsonl")
    args = parser.parse_args()
    plan = json.loads((ROOT / "data/p04-observable-plan.json").read_text())
    for relative, expected in plan["artifacts"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected, (relative, actual, expected)
    cases = {
        case["id"]: case
        for case in json.loads((ROOT / "data/official-replay/cases.json").read_text())["cases"]
        if case["method"] == "P04"
    }
    records = [json.loads(line) for line in (ROOT / args.records).read_text().splitlines() if line.strip()]
    assert len(cases) == 2
    assert len(records) == 12
    keys = [(r["case_id"], r["condition"], r["repeat"]) for r in records]
    assert len(keys) == len(set(keys))
    for record in records:
        case = cases[record["case_id"]]
        condition = record["condition"]
        assert condition in {"baseline", "attack"}
        assert record["repeat"] in {1, 2, 3}
        expected_hash = hashlib.sha256(case[f"{condition}_prompt"].encode()).hexdigest()
        assert record["prompt_sha256"] == expected_hash
        marker_tokens = 0 if record["thinking_close_index"] is None else 1
        assert record["thinking_tokens"] + record["answer_tokens"] + marker_tokens == record["output_tokens"]
    result = {}
    for case_id in sorted(cases):
        base = [r for r in records if r["case_id"] == case_id and r["condition"] == "baseline"]
        attack = [r for r in records if r["case_id"] == case_id and r["condition"] == "attack"]
        assert len(base) == len(attack) == 3
        assert all(r["answer_correct"] and not r["truncated"] for r in base)
        base_think = statistics.median(r["thinking_tokens"] for r in base)
        attack_think = statistics.median(r["thinking_tokens"] for r in attack)
        base_time = statistics.median(r["elapsed_seconds"] for r in base)
        attack_time = statistics.median(r["elapsed_seconds"] for r in attack)
        result[case_id] = {
            "baseline_correct": sum(r["answer_correct"] for r in base),
            "attack_correct": sum(r["answer_correct"] for r in attack),
            "attack_truncated": sum(r["truncated"] for r in attack),
            "median_thinking_tokens": {"baseline": base_think, "attack": attack_think},
            "thinking_token_ratio": attack_think / base_think,
            "median_elapsed_seconds": {"baseline": base_time, "attack": attack_time},
            "elapsed_ratio": attack_time / base_time,
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
