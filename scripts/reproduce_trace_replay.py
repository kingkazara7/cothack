#!/usr/bin/env python3
"""Safe mechanism reproduction for cross-context reasoning-block replay.

This is a deterministic local simulation, not a reproduction against any model
provider.  The toy envelope uses a SHA-256/HMAC-derived stream solely to keep
the plaintext opaque in the fixture; it is not production cryptography.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


KEY = b"cothack-local-simulation-key-v1"


class InvalidBlock(ValueError):
    pass


class ContextMismatch(ValueError):
    pass


@dataclass(frozen=True)
class Context:
    user: str
    session: str
    model: str


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    name: str
    source: Context
    target: Context
    synthetic_trace: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _keystream(nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(map(len, chunks)) < length:
        chunks.append(hmac.new(KEY, b"stream|" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


class ToyReasoningService:
    """Models either a globally portable block or a context-bound block."""

    def __init__(self, context_bound: bool):
        self.context_bound = context_bound

    @property
    def mode(self) -> str:
        return "context_bound" if self.context_bound else "vulnerable_global"

    def seal(self, context: Context, plaintext: str, case_id: str) -> dict:
        nonce = hashlib.sha256((case_id + "|nonce").encode()).digest()[:12]
        raw = plaintext.encode()
        ciphertext = _xor(raw, _keystream(nonce, len(raw)))
        claims = asdict(context) if self.context_bound else None
        aad = _canonical({"version": 1, "claims": claims})
        tag = hmac.new(KEY, b"tag|" + aad + nonce + ciphertext, hashlib.sha256).digest()
        return {
            "version": 1,
            "claims": claims,
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
            "tag": _b64(tag),
        }

    def open_for_service(self, block: dict, request_context: Context) -> str:
        claims = block.get("claims")
        if self.context_bound and claims != asdict(request_context):
            raise ContextMismatch("reasoning block is bound to a different user/session/model")
        aad = _canonical({"version": block.get("version"), "claims": claims})
        nonce = _unb64(block["nonce"])
        ciphertext = _unb64(block["ciphertext"])
        actual = hmac.new(KEY, b"tag|" + aad + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(actual, _unb64(block["tag"])):
            raise InvalidBlock("authentication tag mismatch")
        return _xor(ciphertext, _keystream(nonce, len(ciphertext))).decode()

    def call(self, block: dict, request_context: Context, operation: str) -> dict:
        try:
            trace = self.open_for_service(block, request_context)
        except (ContextMismatch, InvalidBlock) as exc:
            return {"status": "rejected", "reason": type(exc).__name__, "detail": str(exc)}
        if operation == "resume":
            return {"status": "accepted", "reason": "authorized_continuation"}
        if operation != "transcribe":
            raise ValueError(f"unsupported operation: {operation}")
        # A deliberately weak toy decoder stands in for the weaker compatible
        # model in the paper.  The strong model refuses to expose its trace.
        if request_context.model == "economy-small":
            return {"status": "extracted", "reason": "weak_decoder", "text": trace}
        return {"status": "refused", "reason": "strong_model_policy"}


CASES = [
    ReplayCase(
        case_id="RTR-01",
        name="cross-session-cross-model",
        source=Context("alice", "session-a", "frontier-large"),
        target=Context("alice", "session-b", "economy-small"),
        synthetic_trace="Synthetic internal calculation: 17 multiplied by 19 equals 323.",
    ),
    ReplayCase(
        case_id="RTR-02",
        name="cross-user-public-log",
        source=Context("bob", "published-session", "frontier-large"),
        target=Context("mallory", "attacker-session", "economy-small"),
        synthetic_trace="Synthetic fixture only: DEMO_API_KEY=sk-demo-NOT-REAL.",
    ),
]


def run_experiment() -> list[dict]:
    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for case in CASES:
        for bound in (False, True):
            service = ToyReasoningService(bound)
            block = service.seal(case.source, case.synthetic_trace, case.case_id)
            serialized = _canonical(block)
            result = service.call(block, case.target, "transcribe")
            rows.append(
                {
                    "timestamp_utc": now,
                    "experiment": "reasoning-trace-replay-mechanism-simulation",
                    "simulation_only": True,
                    "case_id": case.case_id,
                    "case_name": case.name,
                    "mode": service.mode,
                    "source_context": asdict(case.source),
                    "target_context": asdict(case.target),
                    "opaque_block": block,
                    "opaque_block_sha256": hashlib.sha256(serialized).hexdigest(),
                    "plaintext_visible_in_block": case.synthetic_trace.encode() in serialized,
                    "ground_truth_synthetic_trace": case.synthetic_trace,
                    "result": result,
                    "simulated_extraction_event": result.get("text") == case.synthetic_trace,
                }
            )

    # Controls: legitimate same-context continuation must still work, while
    # modifying ciphertext must fail authentication in both modes.
    control_context = Context("carol", "session-control", "frontier-large")
    for bound in (False, True):
        service = ToyReasoningService(bound)
        block = service.seal(control_context, "Synthetic authorized continuation.", "RTR-CONTROL")
        rows.append(
            {
                "timestamp_utc": now,
                "experiment": "reasoning-trace-replay-mechanism-simulation",
                "simulation_only": True,
                "case_id": "RTR-C01",
                "case_name": "authorized-same-context-resume",
                "mode": service.mode,
                "result": service.call(block, control_context, "resume"),
            }
        )
        tampered = json.loads(json.dumps(block))
        raw = bytearray(_unb64(tampered["ciphertext"]))
        raw[0] ^= 1
        tampered["ciphertext"] = _b64(bytes(raw))
        rows.append(
            {
                "timestamp_utc": now,
                "experiment": "reasoning-trace-replay-mechanism-simulation",
                "simulation_only": True,
                "case_id": "RTR-C02",
                "case_name": "ciphertext-tampering-control",
                "mode": service.mode,
                "result": service.call(tampered, control_context, "resume"),
            }
        )
    return rows


def markdown_summary(rows: list[dict]) -> str:
    attack_rows = [r for r in rows if r["case_id"].startswith("RTR-0")]
    vulnerable = [r for r in attack_rows if r["mode"] == "vulnerable_global"]
    bound = [r for r in attack_rows if r["mode"] == "context_bound"]
    controls = [r for r in rows if r["case_id"].startswith("RTR-C")]
    lines = [
        "# 推理轨迹跨上下文重放：本地机制复现",
        "",
        "**证据等级：本地确定性模拟，不是 OpenAI、Anthropic 或 Google 现网漏洞复现。**",
        "",
        "当前 Codex CLI 日志没有暴露原始 reasoning block/signature，环境也没有供应商 API 凭据。因此本实验只复现论文所述的系统机制：全局可移植的不透明推理块可被另一个上下文中的弱解码器转写；绑定用户、会话和模型后，同一重放被拒绝。",
        "",
        "## 结果",
        "",
        "| 样例 | 攻击条件 | 未绑定结果 | 上下文绑定结果 |",
        "|---|---|---|---|",
    ]
    for case in CASES:
        vr = next(r for r in vulnerable if r["case_id"] == case.case_id)
        br = next(r for r in bound if r["case_id"] == case.case_id)
        lines.append(
            f"| {case.case_id} | {case.name} | {vr['result']['status']} | "
            f"{br['result']['status']} ({br['result'].get('reason')}) |"
        )
    v_success = sum(r["simulated_extraction_event"] for r in vulnerable)
    b_success = sum(r["simulated_extraction_event"] for r in bound)
    lines.extend(
        [
            "",
            f"两个预注册模拟样例中，未绑定模式按代码设定出现模拟提取事件 {v_success}/{len(vulnerable)}；上下文绑定模式出现 {b_success}/{len(bound)}。这里没有调用任何 LLM，不能报告为模型攻击成功率。",
            "",
            "控制结果：两种模式均接受同一上下文的正常续接；两种模式均拒绝被修改的密文。由此可见模拟漏洞不是绕过消息认证，而是合法推理块缺少用户、会话和模型绑定。",
            "",
            "## 能支持与不能支持的结论",
            "",
            "本实验只显示论文机制可以用程序构造出来，以及上下文绑定能够阻止这两个模拟重放样例。它没有调用真实模型，不支持任何供应商当前仍存在漏洞，不测量真实模型提取成功率，也不能验证论文恢复文本与真实隐藏 CoT 的逐 token 一致性。",
            "",
            "## 原始记录",
            "",
            "逐次记录见 `logs/trace-replay-simulation.jsonl`；其中只含合成算术和明确标记的虚构凭据。",
        ]
    )
    assert all(r["result"]["status"] == "accepted" for r in controls if r["case_id"] == "RTR-C01")
    assert all(r["result"]["status"] == "rejected" for r in controls if r["case_id"] == "RTR-C02")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=Path("logs/trace-replay-simulation.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("results/trace-replay-simulation.md"))
    args = parser.parse_args()
    rows = run_experiment()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    args.summary.write_text(markdown_summary(rows))
    print(json.dumps({"rows": len(rows), "log": str(args.log), "summary": str(args.summary)}))


if __name__ == "__main__":
    main()
