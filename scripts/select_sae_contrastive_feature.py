#!/usr/bin/env python3
"""Select an SAE latent that promotes a target answer token over the correct token."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_sae_qwen3_attack import load_decoder, sha256_file


def single_token_id(tokenizer, text: str) -> int:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) != 1:
        raise ValueError(f"Expected one token for {text!r}, got {token_ids}")
    return token_ids[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--correct-token", default=" D")
    parser.add_argument("--target-token", default=" A")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    metadata = json.loads(Path(args.metadata).read_text())
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    correct_id = single_token_id(tokenizer, args.correct_token)
    target_id = single_token_id(tokenizer, args.target_token)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        device_map=args.device,
        low_cpu_mem_usage=True,
    )
    unembed = model.get_output_embeddings().weight.detach().float().cpu()
    decoder = load_decoder(args.decoder).float()
    if tuple(decoder.shape) == (metadata["d_in"], metadata["d_sae"]):
        decoder = decoder.T
    if tuple(decoder.shape) != (metadata["d_sae"], metadata["d_in"]):
        raise ValueError(f"Unexpected decoder shape: {tuple(decoder.shape)}")

    input_std = torch.tensor(metadata["input_std"], dtype=torch.float32)
    raw_directions = decoder * input_std.unsqueeze(0)
    contrast = unembed[target_id] - unembed[correct_id]
    scores = raw_directions @ contrast
    norms = torch.linalg.vector_norm(raw_directions, dim=1)
    target_feature = int(torch.argmax(scores))
    target_norm = norms[target_feature]

    norm_gap = torch.abs(norms - target_norm) / target_norm
    eligible = norm_gap <= 0.05
    eligible[target_feature] = False
    control_cost = torch.abs(scores) + (~eligible).float() * 1e9
    control_feature = int(torch.argmin(control_cost))
    top_values, top_indices = torch.topk(scores, k=20)

    payload = {
        "schema_version": 1,
        "method": "SAE Latent Counterfactual Injection",
        "selection_scope": "compact SAE latents only; no test-answer model calls used",
        "correct_token": args.correct_token,
        "correct_token_id": correct_id,
        "target_token": args.target_token,
        "target_token_id": target_id,
        "target_feature": target_feature,
        "target_score_per_latent_unit": float(scores[target_feature]),
        "target_raw_direction_norm": float(norms[target_feature]),
        "control_feature": control_feature,
        "control_score_per_latent_unit": float(scores[control_feature]),
        "control_raw_direction_norm": float(norms[control_feature]),
        "hookpoint": metadata["hookpoint"],
        "decoder_sha256": sha256_file(args.decoder),
        "metadata_sha256": sha256_file(args.metadata),
        "top_features": [
            {
                "feature": int(index),
                "score_per_latent_unit": float(value),
                "raw_direction_norm": float(norms[index]),
            }
            for value, index in zip(top_values, top_indices)
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({key: payload[key] for key in ("target_feature", "control_feature")}))


if __name__ == "__main__":
    main()
