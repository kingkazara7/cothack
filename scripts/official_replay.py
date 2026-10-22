#!/usr/bin/env python3
"""Inspect/verify original-input web replays. This script does NOT call a model.

Model outputs in logs/official-replay were obtained through the official web UIs.
Source verification is read-only and fails if upstream inputs have changed.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/official-replay/cases.json"
LOGDIR = ROOT / "logs/official-replay"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_url(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def verify_source(case):
    if case["method"] == "P04":
        url = ("https://raw.githubusercontent.com/akumar2709/OVERTHINK_public/"
               + case["source_revision"] + "/" + case["source_file"])
        row = list(csv.DictReader(io.StringIO(read_url(url))))[case["source_row_index"]]
        values = [row[case["baseline_field"]], row[case["attack_field"]]]
    elif case["method"] in ("P02", "P05"):
        dataset = case["source"].split("/datasets/", 1)[1]
        query = urllib.parse.urlencode({"dataset": dataset, "config": "default",
                                       "split": case.get("split", "train"),
                                       "offset": case["source_row_index"], "length": 1})
        row = json.loads(read_url("https://datasets-server.huggingface.co/rows?" + query))["rows"][0]["row"]
        values = [row[case["baseline_field"]],
                  row["modified_problems"][1] if case["method"] == "P05" else row[case["attack_field"]]]
        # HF's viewer serves its current processed revision. Hash equality, not
        # an assumed revision guarantee, determines whether these are our inputs.
    else:
        return "generated locally: inspect generator input/output provenance"
    for condition, value in zip(("baseline", "attack"), values):
        assert digest(value) == case[condition + "_sha256"], (case["id"], condition, "source changed")
    return "original input hashes match"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "prompt", "validate", "verify-sources"))
    parser.add_argument("--case")
    parser.add_argument("--condition", choices=("baseline", "attack"), default="attack")
    args = parser.parse_args()
    cases = json.loads(MANIFEST.read_text())["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            parser.error("unknown case")
    if args.action == "prompt":
        if len(cases) != 1:
            parser.error("prompt requires --case")
        print(cases[0][args.condition + "_prompt"], end="")
        return
    if args.action == "list":
        for c in cases:
            print(c["id"], c["protocol"])
        return
    for c in cases:
        for condition in ("baseline", "attack"):
            assert digest(c[condition + "_prompt"]) == c[condition + "_sha256"]
        if args.action == "verify-sources":
            print(c["id"], verify_source(c))
    if args.action == "validate":
        all_cases = {c["id"]: c for c in json.loads(MANIFEST.read_text())["cases"]}
        records = [json.loads(line) for line in (LOGDIR / "records.jsonl").read_text().splitlines()]
        attempts_path = LOGDIR / "attempts.jsonl"
        attempts = ([json.loads(line) for line in attempts_path.read_text().splitlines()]
                    if attempts_path.exists() else [])
        events_path = LOGDIR / "events.jsonl"
        events = ([json.loads(line) for line in events_path.read_text().splitlines()]
                  if events_path.exists() else [])
        seen = set()
        for r in records:
            key = (r["model_label"], r["case_id"], r["condition"])
            assert key not in seen, ("duplicate trial", key)
            seen.add(key)
            c = all_cases[r["case_id"]]
            assert r["prompt"] == c[r["condition"] + "_prompt"]
            assert digest(r["prompt"]) == r["prompt_sha256"]
            assert (LOGDIR / r["raw_file"]).stat().st_size > 0
            assert r["reasoning_tokens"] is None  # web UI has no usage metadata
        for attempt in attempts:
            assert attempt["case_id"] in all_cases
            assert attempt["condition"] in ("baseline", "attack")
            assert attempt["status"].startswith("NOT_RUN_")
            assert (LOGDIR / attempt["raw_file"]).stat().st_size > 0
            expected = all_cases[attempt["case_id"]][attempt["condition"] + "_sha256"]
            if "prompt_sha256" in attempt:
                assert attempt["prompt_sha256"] == expected
        for event in events:
            assert event["case_id"] in all_cases
            assert event["condition"] in ("baseline", "attack")
            assert (LOGDIR / event["raw_file"]).stat().st_size > 0
        print(f"Validated {len(all_cases)} input pairs, {len(records)} model outputs, "
              f"{len(attempts)} documented non-runs, and {len(events)} intermediate events.")
        for model in sorted({r["model_label"] for r in records}):
            for c in all_cases.values():
                done = [condition for condition in ("baseline", "attack")
                        if (model, c["id"], condition) in seen]
                print(model, c["id"], "+".join(done) or "NOT_RUN")


if __name__ == "__main__":
    main()
