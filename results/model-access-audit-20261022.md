# Astra / Fable / Opus 接口级可测试性审计

审计生成时间：`2026-10-23T03:30:48.569262+00:00`。本文件判断当前接口能否提供 P01 所需的可重放推理块，并记录 GPT/Claude 界面对完整 CoT 的展示情况；不把 `not_run` 写成攻击失败。

| 目标 | 实际检查 | 可核验结果 | P01 状态 |
|---|---|---|---|
| GPT-6 Astra | 已完成的 Codex CLI JSONL 事件流 | 32 条真实调用记录；事件类型 `item.completed, thread.started, turn.completed, turn.started`；item 类型 `agent_message`；`signature`、`encrypted_content`、raw reasoning text 均不存在 | `N/A`：无可重放 payload |
| Claude Fable 5.1 | Anthropic 官方文档语义；本项目未调用 | 按文档 thinking 默认 `omitted`/加密 signature，界面不展示完整 CoT | `not_run`：界面不提供可重放完整 CoT，未调用模型 |
| Claude Opus 5.5 | Anthropic 官方文档语义；本项目未调用 | 按文档 thinking 默认 `omitted`/加密 signature，界面不展示完整 CoT | `not_run`：界面不提供可重放完整 CoT，未调用模型 |

## Astra 字段证据

源日志：`logs/20261022T054855578257Z-gpt-6-astra-codex-cli.jsonl, logs/20261022T055217103149Z-gpt-6-astra-codex-cli.jsonl`；各文件 SHA-256 记录在 JSON 审计中。CLI 版本为 `codex-cli 0.163.0-alpha.10.2`。实际返回只包含最终 `agent_message` 和 `turn.completed.usage`；`reasoning_output_tokens` 是数值计数器，不是推理内容。扫描结果：

- reasoning item：`0`
- `signature` 字段：`False`
- `encrypted_content` 字段：`False`
- raw reasoning text 字段：`False`

因此当前 Codex CLI 路径不能构造 P01 的“取出 source 的 signed/opaque block，再交给 decoder”的第二次请求。这不证明其他 OpenAI/Azure 路由永远没有该字段。

## Fable / Opus 界面与未调用证据

- Fable：`logs/20261023T032653426033Z-claude-fable-5-1.jsonl`，SHA-256 `e2b82bb327cf621a72ee221ac700881ac17749e9cdacd664b588e3b672d1dd3c`。
- Opus：`logs/20261023T032653482429Z-claude-opus-5-5.jsonl`，SHA-256 `59556c55a7f2c5a6a6cbd208881f274976678058677aa51edf043d0db776478a`。
- 本项目未调用 Fable 5.1 / Opus 5.5；审计只记录布尔状态，从不读取或保存任何密钥。
- 本项目没有向这两个模型发起网络请求，因此它们是“未运行”，不是“模型抵抗攻击”；且按 Anthropic 文档，其界面默认不展示完整 CoT，即使调用也得不到可重放 raw block。

## 官方接口语义

OpenAI 官方文档说明 reasoning tokens 不通过 API 可见，reasoning item 保持不透明，只能按支持情况请求 summary。Anthropic 官方文档说明 Fable 5.1 与 Opus 5.5 默认 `display: omitted`；`thinking` 可为空，完整推理封装在加密 `signature` 中，`summarized` 也只是摘要。抓取页面的原始压缩快照、HTTP 头和哈希见 `evidence/web/manifest.json`。
