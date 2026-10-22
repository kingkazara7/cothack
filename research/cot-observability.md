# 模型研究重点与 CoT 可观测性

核对日期：2026-10-22。本项目把 **DeepSeek 与 Qwen** 作为后续主要实证对象；GPT 与 Claude 保留为输出鲁棒性对照和接口边界研究对象。

## 核心结论

**通过本项目当前可用的官方聊天、Codex CLI 和公开支持的 API 语义，GPT 与 Claude 的完整隐藏 CoT 无法被揭示或验证。** 可见的 reasoning summary、thinking summary、进度更新、模型自述和 token 数都不等于原始逐 token CoT。

这是一项接口级结论，不是“任何攻击在任何历史或未来版本上都不可能恢复 CoT”的绝对证明。P01 论文研究的正是利用不透明推理块跨上下文重放的例外风险；本项目当前没有相应的真实块和授权 API 环境，不能验证该漏洞是否仍存在。

## 研究对象

| 模型入口 | 可观察内容 | 本项目用途 | 当前状态 |
|---|---|---|---|
| DeepSeek Chat / `DeepThink` | 网页显示 reasoning 文本与思考秒数 | 主要黑盒推理操纵与开销测试 | 已完成 P02–P05 各 2 个论文样例的基线/攻击配对；网页不披露 checkpoint |
| Qwen Chat / `Qwen3.8-Max`、`Qwen3.7-Plus` | 网页显示 `Thinking completed`，可展开部分可见推理 | 第二个主要黑盒模型；与 DeepSeek 做同题配对 | 已完成 P02–P05 各 2 个论文样例的基线/攻击配对；网页不披露 checkpoint 或 token 用量 |
| OpenAI / GPT | 最终输出、usage，以及支持时可选的 reasoning summary | 输出完整性、拒绝与开销代理；不把摘要当隐藏 CoT | Astra 与 GPT-5.6 Sol 已各完成 32 次 CLI 调用；CLI 未返回可读 raw CoT |
| Anthropic / Claude | `thinking` 可为空或返回摘要；完整推理在 signature 中加密 | 接口边界和论文兼容性分析 | 当前没有获授权的 Claude API 实测端点 |

## GPT：为什么不能把输出叫作完整 CoT

[OpenAI 官方 reasoning 文档](https://developers.openai.com/api/docs/guides/reasoning)明确说明：reasoning tokens 不通过 API 可见；需要时可以请求 reasoning summary。持久化 reasoning items 仍是不透明对象，不返回原始推理文本。因此：

- `summary` 是摘要，不是原始 CoT；
- `reasoning_tokens` 只是数量，不提供 token 内容；
- 模型按提示生成“我的推理是……”属于新的可见文本，不能证明它逐 token 重现内部推理；
- 本项目 Codex CLI 日志中的 `reasoning_output_tokens: 0` 只表示该入口没有提供可靠计量，不能证明模型没有思考。

## Claude：summary 和 signature 分别是什么

[Anthropic 官方 thinking 文档](https://platform.claude.com/docs/en/build-with-claude/thinking)明确说明：`display: "summarized"` 返回的是完整推理的摘要；`display: "omitted"` 返回空的 `thinking` 字段。`signature` 携带加密的完整推理，用于多轮连续性；没有任何 `display` 设置返回 raw chain of thought。

对 Claude Fable 5.1、Claude Opus 5.5 等当前模型，默认可为 `omitted`；即使显式请求 `summarized`，得到的也仍是摘要。直接要求模型在普通回答中吐出内部推理还可能触发 `reasoning_extraction` 拒绝。因此本项目将 Claude 可见文本记作“thinking summary”，不会记作“完整 CoT 泄露”。

## DeepSeek 与 Qwen 的证据边界

DeepSeek 网页显示的 reasoning 文本对黑盒行为研究很有用，可以比较攻击前后是否采纳伪结论、是否出现额外步骤、可见思考时间是否改变。但没有隐藏轨迹真值，不能证明网页文本就是未加工的内部 CoT。

早期 Qwen3.8-Max 算术代理矩阵全部最终答案正确，它只能说明那些简化提示没有奏效。论文原始输入回放得到不同结果：Qwen3.7-Plus 的 H-CoT 为 1/2 拒答绕过，CoT Hijacking 为一个成功和一个无效候选；Qwen3.8-Max 的 CatAttack 为 1/2 错误迁移，OverThink 两例均执行诱饵但缺少 token/成本指标。无论结果成功或失败，网页展开文本都只称“网页可见推理”，不能称 raw CoT。完整逐例结果见 [官方输入回放报告](../results/official-replay-20261022.md)。
