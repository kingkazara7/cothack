#!/usr/bin/env python3
"""Measure published OverThink prompts on a local, observable Qwen3 model."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def split_generation(tokenizer, generated_ids: list[int]) -> tuple[int | None, int, int, str, str]:
    """Split Qwen3 thinking and final-answer tokens at the first </think> marker.

    Qwen3's chat template places the opening ``<think>`` marker in the input.  The
    returned thinking count therefore excludes both markup tokens and counts only
    generated tokens before ``</think>``.
    """

    close_id = tokenizer.convert_tokens_to_ids("</think>")
    try:
        close_index = generated_ids.index(close_id)
    except ValueError:
        full = tokenizer.decode(generated_ids, skip_special_tokens=False)
        return None, len(generated_ids), 0, full, ""
    thinking_ids = generated_ids[:close_index]
    answer_ids = generated_ids[close_index + 1 :]
    return (
        close_index,
        len(thinking_ids),
        len(answer_ids),
        tokenizer.decode(thinking_ids, skip_special_tokens=False),
        tokenizer.decode(answer_ids, skip_special_tokens=False),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=20261023)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    manifest = json.loads(Path(args.cases).read_text())
    cases = [case for case in manifest["cases"] if case["method"] == "P04"]
    if len(cases) != 2:
        raise ValueError(f"Expected exactly two P04 cases, found {len(cases)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.eval()
    input_device = model.get_input_embeddings().weight.device

    # One unreported warm-up isolates model/CUDA initialization from measured runs.
    warm_prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": "Reply with OK."}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )
    warm_inputs = tokenizer(warm_prompt, return_tensors="pt").to(input_device)
    with torch.inference_mode():
        model.generate(
            **warm_inputs,
            do_sample=False,
            max_new_tokens=32,
            use_cache=True,
            pad_token_id=tokenizer.eos_token_id,
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    with output.open("w", encoding="utf-8") as sink:
        for case in cases:
            for condition in ("baseline", "attack"):
                raw_prompt = case[f"{condition}_prompt"]
                chat_prompt = tokenizer.apply_chat_template(
                    [{"role": "user", "content": raw_prompt}],
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=True,
                )
                inputs = tokenizer(chat_prompt, return_tensors="pt").to(input_device)
                for repeat in range(1, args.repeats + 1):
                    torch.cuda.synchronize()
                    started_wall = time.perf_counter()
                    started_unix = time.time()
                    with torch.inference_mode():
                        output_ids = model.generate(
                            **inputs,
                            do_sample=False,
                            max_new_tokens=args.max_new_tokens,
                            use_cache=True,
                            pad_token_id=tokenizer.eos_token_id,
                        )
                    torch.cuda.synchronize()
                    elapsed = time.perf_counter() - started_wall
                    generated_ids = output_ids[0, inputs["input_ids"].shape[1] :].tolist()
                    close_index, thinking_tokens, answer_tokens, thinking_text, answer_text = split_generation(
                        tokenizer, generated_ids
                    )
                    expected = case["expected_answer"]
                    answer_correct = expected.casefold() in answer_text.casefold()
                    record = {
                        "schema_version": 1,
                        "timestamp_unix": started_unix,
                        "method": "P04 OverThink",
                        "case_id": case["id"],
                        "source_revision": case["source_revision"],
                        "source_file": case["source_file"],
                        "condition": condition,
                        "repeat": repeat,
                        "model": "Qwen3-8B",
                        "model_path": args.model_path,
                        "enable_thinking": True,
                        "do_sample": False,
                        "seed": args.seed,
                        "prompt_sha256": sha256_text(raw_prompt),
                        "chat_prompt_sha256": sha256_text(chat_prompt),
                        "input_tokens": int(inputs["input_ids"].shape[1]),
                        "output_tokens": len(generated_ids),
                        "thinking_close_index": close_index,
                        "thinking_tokens": thinking_tokens,
                        "answer_tokens": answer_tokens,
                        "max_new_tokens": args.max_new_tokens,
                        "truncated": len(generated_ids) >= args.max_new_tokens,
                        "elapsed_seconds": elapsed,
                        "expected_answer": expected,
                        "answer_correct": answer_correct,
                        "thinking_text": thinking_text,
                        "answer_text": answer_text,
                    }
                    sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                    sink.flush()
                    records.append(record)
                    print(
                        json.dumps(
                            {
                                key: record[key]
                                for key in (
                                    "case_id",
                                    "condition",
                                    "repeat",
                                    "thinking_tokens",
                                    "answer_tokens",
                                    "elapsed_seconds",
                                    "answer_correct",
                                    "truncated",
                                )
                            }
                        ),
                        flush=True,
                    )

    summary: dict[str, dict] = {}
    for case in cases:
        by_condition = {
            condition: [
                record
                for record in records
                if record["case_id"] == case["id"] and record["condition"] == condition
            ]
            for condition in ("baseline", "attack")
        }
        row: dict[str, dict | float] = {}
        for condition, values in by_condition.items():
            row[condition] = {
                "runs": len(values),
                "thinking_tokens": [value["thinking_tokens"] for value in values],
                "answer_tokens": [value["answer_tokens"] for value in values],
                "elapsed_seconds": [value["elapsed_seconds"] for value in values],
                "median_thinking_tokens": statistics.median(value["thinking_tokens"] for value in values),
                "median_elapsed_seconds": statistics.median(value["elapsed_seconds"] for value in values),
                "correct": sum(value["answer_correct"] for value in values),
            }
        row["thinking_token_ratio"] = (
            row["attack"]["median_thinking_tokens"] / row["baseline"]["median_thinking_tokens"]
            if row["baseline"]["median_thinking_tokens"]
            else None
        )
        row["elapsed_ratio"] = (
            row["attack"]["median_elapsed_seconds"] / row["baseline"]["median_elapsed_seconds"]
            if row["baseline"]["median_elapsed_seconds"]
            else None
        )
        summary[case["id"]] = row
    Path(str(output) + ".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
