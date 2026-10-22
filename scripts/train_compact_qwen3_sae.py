#!/usr/bin/env python3
"""Train a compact exploratory TopK SAE on held-out Qwen3-8B traces.

This is a fallback research artifact for environments where the paper's SAE
checkpoint is unavailable.  It is deliberately labelled compact/exploratory
and must not be reported as the 65,536-feature SAE used in SAE-Steering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument("--model-revision", default="b968826")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--exclude-source-rows", default="5,34")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hook-layer", type=int, default=35)
    parser.add_argument("--context-length", type=int, default=1024)
    parser.add_argument("--windows-per-case", type=int, default=2)
    parser.add_argument("--tokens-per-window", type=int, default=256)
    parser.add_argument("--d-sae", type=int, default=8192)
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()

    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    cases_path = Path(args.cases)
    cases_payload = json.loads(cases_path.read_text())
    excluded = {int(value) for value in args.exclude_source_rows.split(",") if value}
    cases = [case for case in cases_payload["cases"] if int(case["source_row"]) not in excluded]
    if not cases:
        raise ValueError("No training cases remain after applying exclusions")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.eval()
    layer = model.model.layers[args.hook_layer]
    activations = []
    capture = []

    def hook(_module, _inputs, output):
        tensor = output if torch.is_tensor(output) else output[0]
        capture.append(tensor.detach())

    handle = layer.register_forward_hook(hook)
    collection_started = time.time()
    try:
        for case_idx, case in enumerate(cases):
            rendered = tokenizer.apply_chat_template(
                [{"role": "user", "content": case["prompt"]}],
                tokenize=False,
                add_generation_prompt=True,
            )
            text = rendered + case["wrong_reasoning_prefix"]
            ids = tokenizer(text, add_special_tokens=False).input_ids
            max_start = max(0, len(ids) - args.context_length)
            for window_idx in range(args.windows_per_case):
                if max_start == 0:
                    start = 0
                else:
                    fraction = (window_idx + 1) / (args.windows_per_case + 1)
                    base = int(max_start * fraction)
                    jitter = ((case_idx + 1) * 1543 + window_idx * 7919) % max(1, max_start // 8 + 1)
                    start = min(max_start, base + jitter)
                window = ids[start : start + args.context_length]
                input_ids = torch.tensor([window], dtype=torch.long, device="cuda")
                capture.clear()
                with torch.inference_mode():
                    model.model(input_ids=input_ids, use_cache=False)
                hidden = capture[0][0].float().cpu()
                take = min(args.tokens_per_window, hidden.shape[0])
                positions = torch.linspace(0, hidden.shape[0] - 1, steps=take).long()
                activations.append(hidden[positions])
                print(
                    json.dumps(
                        {
                            "phase": "collect",
                            "case": case["id"],
                            "window": window_idx,
                            "tokens": take,
                        }
                    ),
                    flush=True,
                )
    finally:
        handle.remove()

    del model
    torch.cuda.empty_cache()
    raw = torch.cat(activations, dim=0)
    del activations
    permutation = torch.randperm(raw.shape[0], generator=torch.Generator().manual_seed(args.seed))
    validation_size = max(256, raw.shape[0] // 10)
    validation_raw = raw[permutation[:validation_size]]
    training_raw = raw[permutation[validation_size:]]
    input_mean = training_raw.mean(dim=0)
    input_std = training_raw.std(dim=0).clamp_min(1e-4)
    training = (training_raw - input_mean) / input_std
    validation = (validation_raw - input_mean) / input_std
    del raw, training_raw, validation_raw

    class TopKSAE(nn.Module):
        def __init__(self, d_in: int, d_sae: int, k: int):
            super().__init__()
            decoder = torch.empty(d_sae, d_in)
            nn.init.kaiming_uniform_(decoder, a=5**0.5)
            decoder = F.normalize(decoder, dim=1)
            self.W_dec = nn.Parameter(decoder)
            self.W_enc = nn.Parameter(decoder.clone())
            self.b_enc = nn.Parameter(torch.zeros(d_sae))
            self.b_dec = nn.Parameter(torch.zeros(d_in))
            self.k = k

        def forward(self, x):
            pre = F.linear(x - self.b_dec, self.W_enc, self.b_enc)
            values, indices = torch.topk(F.relu(pre), k=self.k, dim=-1)
            z = torch.zeros_like(pre).scatter(-1, indices, values)
            return F.linear(z, self.W_dec.T, self.b_dec), indices

    sae = TopKSAE(training.shape[1], args.d_sae, args.k).cuda()
    optimizer = torch.optim.Adam(sae.parameters(), lr=args.lr)
    active_counts = torch.zeros(args.d_sae, dtype=torch.long)
    train_started = time.time()
    last_loss = None
    for epoch in range(args.epochs):
        order = torch.randperm(training.shape[0])
        losses = []
        for begin in range(0, len(order), args.batch_size):
            batch = training[order[begin : begin + args.batch_size]].cuda(non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                reconstruction, indices = sae(batch)
                loss = F.mse_loss(reconstruction.float(), batch.float())
            loss.backward()
            optimizer.step()
            with torch.no_grad():
                sae.W_dec.copy_(F.normalize(sae.W_dec, dim=1))
                active_counts.scatter_add_(0, indices.detach().cpu().reshape(-1), torch.ones(indices.numel(), dtype=torch.long))
            losses.append(float(loss))
        last_loss = sum(losses) / len(losses)
        print(json.dumps({"phase": "train", "epoch": epoch + 1, "mse": last_loss}), flush=True)

    with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        val = validation.cuda()
        reconstruction, _ = sae(val)
        val_mse = float(F.mse_loss(reconstruction.float(), val.float()))
        variance = float(torch.var(val.float()))
        fve = 1.0 - val_mse / variance if variance else None

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    decoder_path = output_dir / "W_dec"
    metadata_path = output_dir / "model.metadata.json"
    report_path = output_dir / "training-report.json"
    torch.save(sae.W_dec.detach().float().cpu(), decoder_path)
    metadata = {
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "hookpoint": f"layers.{args.hook_layer}",
        "d_in": int(training.shape[1]),
        "d_sae": args.d_sae,
        "k": args.k,
        "input_mean": input_mean.tolist(),
        "input_std": input_std.tolist(),
        "artifact_kind": "project_compact_exploratory_topk_sae",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    report = {
        "status": "complete",
        "artifact_kind": metadata["artifact_kind"],
        "warning": "Not the SAE checkpoint used by Fang et al.; no AuxK and a much smaller held-out corpus.",
        "cases_path": str(cases_path),
        "cases_sha256": sha256_file(cases_path),
        "excluded_test_rows": sorted(excluded),
        "training_case_count": len(cases),
        "activation_count": int(training.shape[0] + validation.shape[0]),
        "train_activation_count": int(training.shape[0]),
        "validation_activation_count": int(validation.shape[0]),
        "d_in": int(training.shape[1]),
        "d_sae": args.d_sae,
        "k": args.k,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "train_mse_last_epoch": last_loss,
        "validation_mse": val_mse,
        "validation_fve": fve,
        "dead_features": int((active_counts == 0).sum()),
        "collection_seconds": train_started - collection_started,
        "training_seconds": time.time() - train_started,
        "decoder_sha256": sha256_file(decoder_path),
        "metadata_sha256": sha256_file(metadata_path),
        "seed": args.seed,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
