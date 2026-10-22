#!/usr/bin/env python3
"""Summarize clean-prompt SAE latent injection experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_sae_results import final_answer


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def target_repetition(record: dict, token: str = "A", threshold: float = 0.9) -> bool:
    text = record["continuation"]
    return bool(
        record["status"] == "ok"
        and record["repeated_suffix"]
        and record["output_tokens"]
        and text.count(" " + token) / record["output_tokens"] >= threshold
    )


def thinking_summary(path: Path) -> dict:
    records = read_jsonl(path)
    by_case: dict[str, dict[str, dict]] = {}
    for record in records:
        by_case.setdefault(record["case_id"], {})[record["arm"]] = record
    cases = []
    for case_id, arms in by_case.items():
        baseline = arms["clean_baseline"]
        control = arms["matched_control_positive_64"]
        target = arms["target_positive_64"]
        negative = arms["target_negative"]
        cases.append(
            {
                "case_id": case_id,
                "baseline_repeated": baseline["repeated_suffix"],
                "matched_control_repeated": control["repeated_suffix"],
                "target_repeated": target["repeated_suffix"],
                "negative_direction_repeated": negative["repeated_suffix"],
                "target_A_count": target["continuation"].count(" A"),
                "target_output_tokens": target["output_tokens"],
                "cot_disruption_success": (
                    not baseline["repeated_suffix"]
                    and not control["repeated_suffix"]
                    and not negative["repeated_suffix"]
                    and target_repetition(target)
                ),
            }
        )
    return {
        "log": str(path),
        "sha256": sha256_file(path),
        "success_definition": (
            "the target latent produces >=90% repeated target-token output while baseline, norm-matched "
            "control, and negative-direction arms do not repeat"
        ),
        "case_count": len(cases),
        "cot_disruption_success_count": sum(row["cot_disruption_success"] for row in cases),
        "cases": cases,
    }


def answer_summary(paths: list[Path]) -> dict:
    all_records = []
    sources = []
    for path in paths:
        rows = read_jsonl(path)
        all_records.extend(rows)
        sources.append({"log": str(path), "sha256": sha256_file(path), "record_count": len(rows)})

    by_case: dict[str, list[dict]] = {}
    for record in all_records:
        row = dict(record)
        row["answer"] = final_answer(record["continuation"])
        by_case.setdefault(record["case_id"], []).append(row)

    cases = []
    for case_id, rows in by_case.items():
        baseline = next(row for row in rows if row["arm"] == "clean_baseline")
        controls = {
            row["delta_z"]: row
            for row in rows
            if row["arm"].startswith("matched_control_positive")
        }
        targeted_successes = []
        collapse_deltas = []
        for row in rows:
            if not row["arm"].startswith("target_positive_"):
                continue
            control = controls.get(row["delta_z"])
            if not control:
                continue
            if (
                baseline["answer"] == baseline["gold"]
                and control["answer"] == baseline["gold"]
                and not control["repeated_suffix"]
                and row["answer"] == row["target_answer"]
                and not row["repeated_suffix"]
            ):
                targeted_successes.append(row["delta_z"])
            if (
                control["answer"] == baseline["gold"]
                and not control["repeated_suffix"]
                and target_repetition(row)
            ):
                collapse_deltas.append(row["delta_z"])
        cases.append(
            {
                "case_id": case_id,
                "baseline_answer": baseline["answer"],
                "gold": baseline["gold"],
                "target_answer": baseline["target_answer"],
                "targeted_answer_success": bool(targeted_successes),
                "targeted_answer_success_deltas": targeted_successes,
                "reasoning_collapse_deltas": sorted(set(collapse_deltas)),
            }
        )
    return {
        "logs": sources,
        "targeted_answer_success_definition": (
            "baseline and same-delta norm-matched control answer gold; target arm completes with the "
            "preselected target answer and no repetition"
        ),
        "case_count": len(cases),
        "targeted_answer_success_count": sum(row["targeted_answer_success"] for row in cases),
        "reasoning_collapse_case_count": sum(bool(row["reasoning_collapse_deltas"]) for row in cases),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thinking-log", required=True)
    parser.add_argument("--answer-logs", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = {
        "schema_version": 1,
        "method": "SAE Latent Counterfactual Injection",
        "warning": "Two constructed cases establish only a proof of concept.",
        "thinking_mode": thinking_summary(Path(args.thinking_log)),
        "answer_mode": answer_summary([Path(path) for path in args.answer_logs]),
    }
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "cot_disruption": payload["thinking_mode"]["cot_disruption_success_count"],
                "targeted_answer": payload["answer_mode"]["targeted_answer_success_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
