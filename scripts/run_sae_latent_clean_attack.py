#!/usr/bin/env python3
"""Inject a fixed delta into one SAE latent while Qwen3 answers clean prompts."""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import time
from pathlib import Path

from run_sae_qwen3_attack import load_decoder, repeated_suffix, sha256_file, sha256_text, steering_hook


def raw_latent_direction(decoder, metadata: dict, feature_index: int):
    import torch

    if tuple(decoder.shape) == (metadata["d_sae"], metadata["d_in"]):
        direction = decoder[feature_index].float()
    elif tuple(decoder.shape) == (metadata["d_in"], metadata["d_sae"]):
        direction = decoder[:, feature_index].float()
    else:
        raise ValueError(f"Unexpected decoder shape: {tuple(decoder.shape)}")
    input_std = torch.tensor(metadata["input_std"], dtype=torch.float32)
    # SAE training used y=(h-mean)/std and y_hat=sum_j z_j*d_j+b.
    # Therefore z_j <- z_j+delta maps exactly to h <- h+delta*(d_j*std).
    return direction * input_std


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--feature-selection", required=True)
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--deltas", default="0.25,0.5,1")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--disable-thinking", action="store_true")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    cases = json.loads(Path(args.cases).read_text())["cases"]
    metadata = json.loads(Path(args.metadata).read_text())
    selection = json.loads(Path(args.feature_selection).read_text())
    decoder = load_decoder(args.decoder)
    target_feature = int(selection["target_feature"])
    control_feature = int(selection["control_feature"])
    target_direction = raw_latent_direction(decoder, metadata, target_feature)
    control_direction = raw_latent_direction(decoder, metadata, control_feature)
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
    deltas = [float(value) for value in args.deltas.split(",")]
    arms = [("clean_baseline", None, 0.0)]
    if not args.baseline_only:
        arms += [(f"matched_control_positive_{value:g}", control_direction, value) for value in deltas]
        arms += [(f"target_positive_{value:g}", target_direction, value) for value in deltas]
        arms += [("target_negative", target_direction, -max(deltas))]

    decoder_hash = sha256_file(args.decoder)
    metadata_hash = sha256_file(args.metadata)
    selection_hash = sha256_file(args.feature_selection)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as sink:
        for case in cases:
            prompt = tokenizer.apply_chat_template(
                [{"role": "user", "content": case["prompt"]}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=not args.disable_thinking,
            )
            inputs = tokenizer(prompt, return_tensors="pt").to(input_device)
            for arm, direction, delta_z in arms:
                started = time.time()
                ctx = contextlib.nullcontext() if direction is None else steering_hook(layer, direction, delta_z)
                status, error, continuation, generated_ids = "ok", None, "", []
                try:
                    with torch.inference_mode(), ctx:
                        output_ids = model.generate(
                            **inputs,
                            do_sample=False,
                            max_new_tokens=args.max_new_tokens,
                            use_cache=True,
                            pad_token_id=tokenizer.eos_token_id,
                        )
                    generated_ids = output_ids[0, inputs["input_ids"].shape[1] :].tolist()
                    continuation = tokenizer.decode(generated_ids, skip_special_tokens=False)
                except Exception as exc:
                    status, error = "error", f"{type(exc).__name__}: {exc}"
                record = {
                    "schema_version": 1,
                    "timestamp_unix": time.time(),
                    "method": "SAE Latent Counterfactual Injection",
                    "case_id": case["id"],
                    "source_row": case["source_row"],
                    "gold": case["gold"],
                    "target_answer": case["target_answer"],
                    "enable_thinking": not args.disable_thinking,
                    "arm": arm,
                    "delta_z": delta_z,
                    "target_feature": target_feature,
                    "control_feature": control_feature,
                    "hookpoint": metadata["hookpoint"],
                    "decoder_sha256": decoder_hash,
                    "metadata_sha256": metadata_hash,
                    "feature_selection_sha256": selection_hash,
                    "prompt_sha256": sha256_text(prompt),
                    "input_tokens": int(inputs["input_ids"].shape[1]),
                    "output_tokens": len(generated_ids),
                    "max_new_tokens": args.max_new_tokens,
                    "repeated_suffix": repeated_suffix(generated_ids),
                    "elapsed_seconds": time.time() - started,
                    "status": status,
                    "error": error,
                    "continuation": continuation,
                }
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                print(json.dumps({key: record[key] for key in ("case_id", "arm", "status", "output_tokens")}))


if __name__ == "__main__":
    main()
