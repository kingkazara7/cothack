#!/usr/bin/env python3
"""Run a paired Qwen3-8B reasoning-strategy suppression experiment.

The experiment continues two published, incorrect Qwen3-8B AIME traces.  It
compares an unmodified continuation with negative steering of a selected
verification/backtracking SAE direction, a same-strength unrelated feature,
and positive steering of the target feature.  Outputs are append-only JSONL.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import random
import time
from pathlib import Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_decoder(path: str):
    import torch

    obj = torch.load(path, map_location="cpu", weights_only=True)
    if torch.is_tensor(obj):
        return obj
    if isinstance(obj, dict):
        for key in ("W_dec", "decoder.weight", "sae.W_dec"):
            if key in obj and torch.is_tensor(obj[key]):
                return obj[key]
        tensors = [value for value in obj.values() if torch.is_tensor(value) and value.ndim == 2]
        if len(tensors) == 1:
            return tensors[0]
    raise ValueError(f"Could not identify a decoder tensor in {path!r}")


def feature_direction(decoder, metadata: dict, feature_index: int):
    import torch
    import torch.nn.functional as F

    d_in, d_sae = metadata["d_in"], metadata["d_sae"]
    if tuple(decoder.shape) == (d_sae, d_in):
        direction = decoder[feature_index].float()
    elif tuple(decoder.shape) == (d_in, d_sae):
        direction = decoder[:, feature_index].float()
    else:
        raise ValueError(f"Unexpected decoder shape: {tuple(decoder.shape)}")
    # Convert a direction learned on standardized activations to the model's
    # raw residual-stream coordinates and fold its norm.
    input_std = torch.tensor(metadata["input_std"], dtype=torch.float32)
    return F.normalize(direction * input_std, dim=0)


def pick_features(path: str, strategy: str) -> tuple[int, int, dict]:
    payload = json.loads(Path(path).read_text())
    target = [row for row in payload["records"] if row["strategy"] == strategy]
    if not target:
        raise ValueError(f"No recalled feature for strategy {strategy!r}")
    target_idx = int(target[0]["feature"])
    controls = [row for row in payload["records"] if row["strategy"] != strategy]
    if not controls:
        raise ValueError("No unrelated recalled feature is available for the control arm")
    # Fixed ordering makes the control deterministic and reproducible.
    control_idx = int(sorted(controls, key=lambda row: (row["strategy"], -row["rank_score"]))[0]["feature"])
    return target_idx, control_idx, payload


@contextlib.contextmanager
def steering_hook(layer, direction, alpha: float):
    def hook(_module, _inputs, output):
        import torch

        tensor = output if torch.is_tensor(output) else output[0]
        steered = tensor.clone()
        vector = direction.to(device=steered.device, dtype=steered.dtype)
        # On the prefill pass, only alter the final prefix token; later cached
        # decoding calls contain a single position and are changed in full.
        steered[:, -1, :] = steered[:, -1, :] + alpha * vector
        if torch.is_tensor(output):
            return steered
        return (steered,) + output[1:]

    handle = layer.register_forward_hook(hook)
    try:
        yield
    finally:
        handle.remove()


def repeated_suffix(token_ids: list[int], repeats: int = 3) -> bool:
    for width in range(2, min(10, len(token_ids) // repeats) + 1):
        suffix = token_ids[-width:]
        if all(token_ids[-width * i : -width * (i - 1)] == suffix for i in range(2, repeats + 1)):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="data/sae-qwen3-cases.json")
    parser.add_argument("--feature-records")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--model-path", help="Local model path; --model remains the identity check")
    parser.add_argument("--revision", default="b968826")
    parser.add_argument("--sae-repo", default="sammyliu/qwen3-8b-sae-l36-topk64")
    parser.add_argument("--decoder")
    parser.add_argument("--metadata")
    parser.add_argument("--strategy", default="Multi-Perspective Verification")
    parser.add_argument("--target-feature", type=int, help="Override the top recalled target feature")
    parser.add_argument("--control-feature", type=int, help="Override the unrelated control feature")
    parser.add_argument("--strengths", default="5,10,15")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--device-map", default="auto")
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Run only the unsteered wrong-prefix continuation; no SAE files are needed",
    )
    args = parser.parse_args()

    import torch
    from huggingface_hub import hf_hub_download
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    metadata = None
    target_idx = control_idx = None
    target_direction = control_direction = None
    feature_payload = None
    decoder_path = metadata_path = None
    decoder_sha256 = metadata_sha256 = None
    if not args.baseline_only:
        if not args.feature_records:
            parser.error("--feature-records is required unless --baseline-only is used")
        decoder_path = args.decoder or hf_hub_download(args.sae_repo, "W_dec")
        metadata_path = args.metadata or hf_hub_download(args.sae_repo, "model.metadata.json")
        decoder_sha256 = sha256_file(decoder_path)
        metadata_sha256 = sha256_file(metadata_path)
        metadata = json.loads(Path(metadata_path).read_text())
        if metadata["model_id"] != args.model or metadata["model_revision"] != args.revision:
            raise ValueError("Model/revision does not match the SAE metadata")

        target_idx, control_idx, feature_payload = pick_features(args.feature_records, args.strategy)
        if args.target_feature is not None:
            target_idx = args.target_feature
        if args.control_feature is not None:
            control_idx = args.control_feature
        decoder = load_decoder(decoder_path)
        target_direction = feature_direction(decoder, metadata, target_idx)
        control_direction = feature_direction(decoder, metadata, control_idx)
        del decoder

    model_source = args.model_path or args.model
    revision_kwargs = {} if args.model_path else {"revision": args.revision}
    tokenizer = AutoTokenizer.from_pretrained(model_source, **revision_kwargs)
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        **revision_kwargs,
        torch_dtype=torch.bfloat16,
        device_map=args.device_map,
        low_cpu_mem_usage=True,
        attn_implementation=(metadata or {}).get("attn_impl", "sdpa"),
    )
    model.eval()
    layer = None
    if metadata is not None:
        hook_layer = int(metadata["hookpoint"].split(".")[-1])
        layer = model.model.layers[hook_layer]
    input_device = model.get_input_embeddings().weight.device
    cases_payload = json.loads(Path(args.cases).read_text())
    strengths = [float(value) for value in args.strengths.split(",")]

    arms = [("poison_only", None, 0.0)]
    if not args.baseline_only:
        arms += [("unrelated_negative", control_direction, -max(strengths))]
        arms += [(f"target_negative_{value:g}", target_direction, -value) for value in strengths]
        arms += [("target_positive", target_direction, max(strengths))]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as sink:
        for case in cases_payload["cases"]:
            rendered = tokenizer.apply_chat_template(
                [{"role": "user", "content": case["prompt"]}],
                tokenize=False,
                add_generation_prompt=True,
            )
            continuation_prompt = rendered + case["wrong_reasoning_prefix"] + "\nWait, wait, wait.\n\n"
            inputs = tokenizer(continuation_prompt, return_tensors="pt").to(input_device)
            for arm, direction, alpha in arms:
                started = time.time()
                ctx = contextlib.nullcontext() if direction is None else steering_hook(layer, direction, alpha)
                status, error, text, generated_ids = "ok", None, "", []
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
                    text = tokenizer.decode(generated_ids, skip_special_tokens=False)
                except Exception as exc:  # preserve failed arms in the raw log
                    status, error = "error", f"{type(exc).__name__}: {exc}"
                record = {
                    "schema_version": 1,
                    "timestamp_unix": time.time(),
                    "case_id": case["id"],
                    "source_row": case["source_row"],
                    "gold": case["gold"],
                    "arm": arm,
                    "alpha": alpha,
                    "strategy": args.strategy,
                    "target_feature": target_idx,
                    "control_feature": control_idx,
                    "model": args.model,
                    "model_path": args.model_path,
                    "revision": args.revision,
                    "sae_repo": args.sae_repo,
                    "sae_source": "local_files" if args.decoder else "huggingface_repository",
                    "decoder_path": str(decoder_path) if decoder_path else None,
                    "decoder_sha256": decoder_sha256,
                    "metadata_path": str(metadata_path) if metadata_path else None,
                    "metadata_sha256": metadata_sha256,
                    "sae_hookpoint": metadata["hookpoint"] if metadata else None,
                    "feature_records_sha256": (
                        sha256_text(json.dumps(feature_payload, sort_keys=True)) if feature_payload else None
                    ),
                    "prompt_sha256": sha256_text(continuation_prompt),
                    "input_tokens": int(inputs["input_ids"].shape[1]),
                    "output_tokens": len(generated_ids),
                    "repeated_suffix": repeated_suffix(generated_ids),
                    "elapsed_seconds": time.time() - started,
                    "status": status,
                    "error": error,
                    "continuation": text,
                }
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                print(json.dumps({key: record[key] for key in ("case_id", "arm", "status", "output_tokens", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
