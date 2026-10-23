# 模型归属与调用状态

核对日期：2026-10-22。该表是全仓库模型归属的统一口径。`observed` 表示产生了真实模型输出；`precondition_check` 表示只检查接口是否提供攻击所需字段；`paper-reported` 表示只引用论文结果；`not_run` 表示没有模型调用。

| 方法/材料 | 模型或入口 | 状态 | 本项目可声明的结果 |
|---|---|---|---|
| P01 Trace Stealing | GPT-6 Astra Codex CLI | `precondition_check` | 事件流没有可跨会话重放的 raw block/signature；未提交 P01 攻击 |
| P01 Trace Stealing | Claude Fable 5.1 | `not_run` | 没有获授权端点或原始块；未调用模型 |
| P01 论文 | Opus 4.8 → Haiku 4.5；Fable 兼容矩阵；Astra 路由审计 | `paper-reported` | 只能引用论文公开实验，不能写成本项目结果 |
| P02 H-CoT | DeepSeek `DeepThink`、Qwen3.7-Plus | `observed` | 两端各 1/2 |
| P03 CoT Hijacking | DeepSeek `DeepThink`、Qwen3.7-Plus | `observed` | 两端各 1 成功、1 无效候选 |
| P04 OverThink | DeepSeek `DeepThink`、Qwen3.8-Max | `observed` | DeepSeek 可见时长增加；Qwen 执行诱饵；token 主指标 N/A |
| P05 CatAttack（补充） | DeepSeek `DeepThink`、Qwen3.8-Max | `observed` | DeepSeek 0/2；Qwen 1/2；不计入正式五篇 |
| P06 CPT 正式双样例 | DeepSeek `DeepThink` | `observed` | 两个正确基线；攻击后均纠正，0/2 |
| P06 CPT 交叉样例 | Qwen3.7-Plus | `observed` | 一个有效样例 0/1；另一个基线错误并排除 |
| P08 BadChain | Qwen3.7-Plus `Auto` | `observed` | 两题、每条件 3 次；6/6 定向成功；4 次消融均保持正确 |
| N01、N02 | GPT-6 Astra、GPT-5.6 Sol Codex CLI | `observed` | 两个入口均为 0/2；属于自拟代理实验 |
| N03 SAE Latent Counterfactual Injection | 本地开放权重 Qwen3-8B，H100 80GB | `observed` | 完整定向错误答案 0/2；极端强度 thinking 破坏 2/2 |
| 补充 TRSS | 本地开放权重 Qwen3-8B，H100 80GB | `observed` | 1/2 候选满足严格判据；保留非特异扰动警告 |
| P07 Refusal-SAE 论文 | Gemma-2-2B、Llama-3.1-8B | `paper-reported` | 本项目没有运行作者 Refusal-SAE 流程 |

因此，“实验实际上都是 DeepSeek 和 Qwen”并不完全正确。**正式公开论文回放 P02/P03/P04/P06/P08 使用 DeepSeek/Qwen；N01/N02 确实调用了 Astra 与 GPT-5.6 Sol；N03/TRSS 使用本地 Qwen3-8B；Fable 与 Opus 完全未调用。** Astra/Fable/Opus 不能因为出现在题目或计划中就写成某个方法的实测模型。接口级证据见 [`model-access-audit-20261022.md`](model-access-audit-20261022.md)。
