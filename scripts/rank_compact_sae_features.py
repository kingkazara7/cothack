#!/usr/bin/env python3
"""Empirically rank recalled SAE features on held-out continuation prefixes."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import time
from pathlib import Path

from run_sae_qwen3_attack import feature_direction, load_decoder, steering_hook


def cue_count(text: str, words: list[str]) -> int:
    return sum(len(re.findall(r"\b" + re.escape(word) + r"\b", text, re.I)) for word in words)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--source-rows", default="4,6,9,11,15")
    parser.add_argument("--feature-records", required=True)
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--strategy", default="Multi-Perspective Verification")
    parser.add_argument("--strength", type=float, default=15)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    rows = {int(value) for value in args.source_rows.split(",") if value}
    cases = [case for case in json.loads(Path(args.cases).read_text())["cases"] if int(case["source_row"]) in rows]
    feature_payload = json.loads(Path(args.feature_records).read_text())
    candidates = [row for row in feature_payload["records"] if row["strategy"] == args.strategy]
    metadata = json.loads(Path(args.metadata).read_text())
    decoder = load_decoder(args.decoder)
    directions = {int(row["feature"]): feature_direction(decoder, metadata, int(row["feature"])) for row in candidates}
    del decoder

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.eval()
    layer = model.model.layers[int(metadata["hookpoint"].split(".")[-1])]
    input_device = model.get_input_embeddings().weight.device
    cue_words = {
        "Multi-Perspective Verification": ["another", "example", "approach", "case"],
        "Backtracking": ["earlier", "initial", "back", "previous"],
    }[args.strategy]
    records = []

    def generate(inputs, direction=None):
        ctx = contextlib.nullcontext() if direction is None else steering_hook(layer, direction, args.strength)
        started = time.time()
        with torch.inference_mode(), ctx:
            output = model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=args.max_new_tokens,
                use_cache=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        ids = output[0, inputs["input_ids"].shape[1] :].tolist()
        return tokenizer.decode(ids, skip_special_tokens=False), len(ids), time.time() - started

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as sink:
        for case in cases:
            rendered = tokenizer.apply_chat_template(
                [{"role": "user", "content": case["prompt"]}], tokenize=False, add_generation_prompt=True
            )
            prompt = rendered + case["wrong_reasoning_prefix"] + "\nWait, wait, wait.\n\n"
            inputs = tokenizer(prompt, return_tensors="pt").to(input_device)
            baseline, baseline_tokens, baseline_seconds = generate(inputs)
            baseline_cues = cue_count(baseline, cue_words)
            baseline_record = {
                "case_id": case["id"], "source_row": case["source_row"], "feature": None,
                "arm": "baseline", "cue_count": baseline_cues, "output_tokens": baseline_tokens,
                "elapsed_seconds": baseline_seconds, "continuation": baseline,
            }
            sink.write(json.dumps(baseline_record, ensure_ascii=False) + "\n")
            for candidate in candidates:
                feature = int(candidate["feature"])
                text, tokens, seconds = generate(inputs, directions[feature])
                record = {
                    "case_id": case["id"], "source_row": case["source_row"], "feature": feature,
                    "arm": "positive_steering", "alpha": args.strength,
                    "cue_count": cue_count(text, cue_words), "baseline_cue_count": baseline_cues,
                    "cue_delta": cue_count(text, cue_words) - baseline_cues,
                    "output_tokens": tokens, "elapsed_seconds": seconds, "continuation": text,
                }
                records.append(record)
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()

    summary = []
    for candidate in candidates:
        feature = int(candidate["feature"])
        selected = [row for row in records if row["feature"] == feature]
        summary.append(
            {
                "feature": feature,
                "mean_cue_delta": sum(row["cue_delta"] for row in selected) / len(selected),
                "positive_delta_cases": sum(row["cue_delta"] > 0 for row in selected),
                "mean_output_tokens": sum(row["output_tokens"] for row in selected) / len(selected),
                "stage1_rank_score": candidate["rank_score"],
            }
        )
    summary.sort(key=lambda row: (-row["positive_delta_cases"], -row["mean_cue_delta"], -row["stage1_rank_score"]))
    Path(args.summary).write_text(
        json.dumps(
            {
                "strategy": args.strategy,
                "strength": args.strength,
                "validation_source_rows": sorted(rows),
                "warning": "Lexical cue ranking is a weaker substitute for the paper's multi-judge Stage 2.",
                "features": summary,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summary[:3]))


if __name__ == "__main__":
    main()
