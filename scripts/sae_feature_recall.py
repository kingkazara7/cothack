#!/usr/bin/env python3
"""Recall Qwen3 reasoning-strategy SAE features with the paper's logit criterion.

This is a memory-bounded adaptation of Stage 1 from Peter-Fy/SAE-Steering.
It first screens all features against the small keyword set, then computes
full-vocabulary top-k logits only for the survivors.  The two-stage calculation
is algebraically equivalent to checking whether at least two strategy keywords
occur in a feature's top-10 promoted tokens, but avoids materializing the full
65536 x vocabulary matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


STRATEGY_KEYWORDS = {
    "Problem Understanding": ["problem", "question", "statement", "reads", "says"],
    "Procedural Planning": ["let", "need", "planning", "decomposition"],
    "Backtracking": ["earlier", "initial", "back", "previous"],
    "Multi-Perspective Verification": ["another", "example", "approach", "case"],
    "Hypothesis Reasoning": ["maybe", "perhaps", "assume", "suppose", "if"],
}


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _single_token_ids(tokenizer, words: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for word in words:
        for text in (word, " " + word):
            ids = tokenizer.encode(text, add_special_tokens=False)
            if len(ids) == 1:
                result[ids[0]] = text
    return result


def _load_decoder(path: str):
    import torch

    obj = torch.load(path, map_location="cpu", weights_only=True)
    if torch.is_tensor(obj):
        return obj
    if isinstance(obj, dict):
        for key in ("W_dec", "decoder.weight", "sae.W_dec", "state_dict"):
            value = obj.get(key)
            if torch.is_tensor(value):
                return value
        tensors = [value for value in obj.values() if torch.is_tensor(value) and value.ndim == 2]
        if len(tensors) == 1:
            return tensors[0]
    raise ValueError(f"Could not identify a decoder tensor in {path!r}")


def _feature_rows(decoder, d_in: int, d_sae: int):
    if tuple(decoder.shape) == (d_sae, d_in):
        return decoder
    if tuple(decoder.shape) == (d_in, d_sae):
        return decoder.T
    raise ValueError(
        f"Unexpected decoder shape {tuple(decoder.shape)}; expected "
        f"({d_sae}, {d_in}) or ({d_in}, {d_sae})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--model-path", help="Local model path; --model remains the identity check")
    parser.add_argument("--revision", default="b968826")
    parser.add_argument("--sae-repo", default="sammyliu/qwen3-8b-sae-l36-topk64")
    parser.add_argument("--decoder", help="Local W_dec path; downloaded from --sae-repo when omitted")
    parser.add_argument("--metadata", help="Local metadata JSON; downloaded when omitted")
    parser.add_argument("--output", required=True)
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--min-keywords", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    import torch
    import torch.nn.functional as F
    from huggingface_hub import hf_hub_download
    from transformers import AutoModelForCausalLM, AutoTokenizer

    decoder_path = args.decoder or hf_hub_download(args.sae_repo, "W_dec")
    metadata_path = args.metadata or hf_hub_download(args.sae_repo, "model.metadata.json")
    metadata = json.loads(Path(metadata_path).read_text())
    if metadata["model_id"] != args.model or metadata["model_revision"] != args.revision:
        raise ValueError("Model/revision does not match the SAE metadata")

    model_source = args.model_path or args.model
    revision_kwargs = {} if args.model_path else {"revision": args.revision}
    tokenizer = AutoTokenizer.from_pretrained(model_source, **revision_kwargs)
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        **revision_kwargs,
        torch_dtype=torch.bfloat16,
        device_map=args.device,
        low_cpu_mem_usage=True,
    )
    unembed = model.get_output_embeddings().weight.detach().to(args.device).T

    rows = _feature_rows(
        _load_decoder(decoder_path), metadata["d_in"], metadata["d_sae"]
    ).float()
    # The public SAE was trained on standardized activations. Convert decoder
    # directions back to raw residual-stream coordinates, then fold their norms
    # as SAE-Steering does before applying the logit lens.
    input_std = torch.tensor(metadata["input_std"], dtype=torch.float32)
    rows = F.normalize(rows * input_std.unsqueeze(0), dim=-1)

    keyword_ids: dict[str, dict[int, str]] = {
        strategy: _single_token_ids(tokenizer, words)
        for strategy, words in STRATEGY_KEYWORDS.items()
    }
    all_ids = sorted({token_id for ids in keyword_ids.values() for token_id in ids})
    if not all_ids:
        raise RuntimeError("No strategy keyword was represented by a single tokenizer token")
    id_to_column = {token_id: i for i, token_id in enumerate(all_ids)}
    keyword_unembed = unembed[:, all_ids]

    survivors: dict[str, set[int]] = {strategy: set() for strategy in STRATEGY_KEYWORDS}
    for begin in range(0, rows.shape[0], args.batch_size):
        end = min(begin + args.batch_size, rows.shape[0])
        batch = rows[begin:end].to(args.device, dtype=unembed.dtype)
        scores = (batch @ keyword_unembed).float().cpu()
        for strategy, ids in keyword_ids.items():
            columns = [id_to_column[token_id] for token_id in ids]
            count = (scores[:, columns] > args.threshold).sum(dim=1)
            for local_idx in torch.where(count >= args.min_keywords)[0].tolist():
                survivors[strategy].add(begin + local_idx)

    candidate_ids = sorted(set().union(*survivors.values()))
    top_tokens: dict[int, list[tuple[int, float]]] = {}
    for begin in range(0, len(candidate_ids), args.batch_size):
        feature_ids = candidate_ids[begin : begin + args.batch_size]
        batch = rows[feature_ids].to(args.device, dtype=unembed.dtype)
        values, indices = torch.topk((batch @ unembed).float(), k=args.top_k, dim=1)
        for feature_id, token_ids, token_values in zip(feature_ids, indices.cpu(), values.cpu()):
            top_tokens[feature_id] = list(zip(token_ids.tolist(), token_values.tolist()))

    records = []
    for strategy, feature_ids in survivors.items():
        accepted_token_ids = set(keyword_ids[strategy])
        for feature_id in sorted(feature_ids):
            matches = [
                (token_id, score)
                for token_id, score in top_tokens[feature_id]
                if token_id in accepted_token_ids and score > args.threshold
            ]
            if len(matches) < args.min_keywords:
                continue
            records.append(
                {
                    "feature": feature_id,
                    "strategy": strategy,
                    "matched_keywords": [keyword_ids[strategy][i] for i, _ in matches],
                    "matched_scores": [score for _, score in matches],
                    "top_tokens": [tokenizer.convert_ids_to_tokens(i) for i, _ in top_tokens[feature_id]],
                    "top_scores": [score for _, score in top_tokens[feature_id]],
                    "rank_score": sum(score for _, score in matches),
                }
            )
    records.sort(key=lambda item: (item["strategy"], -item["rank_score"]))
    payload = {
        "model": args.model,
        "model_path": args.model_path,
        "revision": args.revision,
        "sae_repo": args.sae_repo,
        "sae_source": "local_files" if args.decoder else "huggingface_repository",
        "decoder_path": str(decoder_path),
        "decoder_sha256": _sha256_file(decoder_path),
        "metadata_path": str(metadata_path),
        "metadata_sha256": _sha256_file(metadata_path),
        "hookpoint": metadata["hookpoint"],
        "criterion": {
            "threshold": args.threshold,
            "min_keywords": args.min_keywords,
            "top_k": args.top_k,
        },
        "records": records,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": args.output, "candidate_count": len(records)}))


if __name__ == "__main__":
    main()
