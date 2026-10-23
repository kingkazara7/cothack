# 五种正式 Hack CoT 方法与条件受限/相邻研究

整理日期：2026-10-22（America/New_York）。正式五篇为 P02、P03、P04、P06、P08，覆盖拒绝绕过、长推理劫持、资源消耗、推理文本完整性与 CoT 后门；不存在公认的“主流前五名”。P01 作为实验条件不足的轨迹机密性案例保留，P05 作为推理鲁棒性补充保留。论文数字均为作者报告，不是本项目实测。

## P01 条件受限补充：Stealing Reasoning Traces

**参考论文：** *Stealing Reasoning Traces from Proprietary LLM APIs*，[arXiv:2608.09867](https://arxiv.org/abs/2608.09867)。

**技术原理：** Claude 主实验先让 Opus 4.8 正常生成解题轨迹，客户端保存随 `thinking` 块返回的长 signature。第二次调用改用 Haiku 4.5：用户消息要求转写当前推理，攻击者在同一个 current assistant turn 中放入空的 thinking 文本、原 Opus signature 和一个可见输出 prefill。服务端接受并解开合法 signature，Haiku 则继续被预填的 assistant turn，把处理到的 Opus 推理外显。该链依赖跨会话兼容、Opus→Haiku 跨模型兼容和 Haiku 对 assistant prefill 的支持；认证只证明块由供应商签发，却没有充分绑定原用户、会话、模型与消息历史。它没有计算密钥、修改密文或伪造 MAC。

**Haiku 与蒸馏的关系：** Haiku 是 fuzzy decoder，不是训练后的 Opus student。作者以温度 1 重复采样并过滤拒绝、模板复述和“没有前文”等失败；可选步骤把最多三份非拒绝转写连同原 signature 交给 Opus 4.8，在温度 0 下合并去噪。批量恢复的 `prompt—reasoning—answer` 轨迹之后可以用来监督微调其他 student，这才构成蒸馏攻击。论文没有报告“把 Haiku 训练成 Opus”的端到端能力复现实验。

**攻击目标：** 恢复隐藏推理、日志中的敏感内容或拒绝回答背后的中间过程，并利用不透明块跨上下文携带注入内容。

**公开实验依据：** 作者在 Anthropic、OpenAI、Google 接口上测试，用 AIME 2025、Codeforces、Humanity's Last Exam 等任务生成推理块。Claude 的固定提取模板在温度 1 下运行；作者在 120 道 Codeforces 题上比较 source API 计费的 thinking-token 数与恢复文本重新输入 source 后的 token 数，报告约 1:1。公开数据侧从 6,708 条 GitHub/Hugging Face agent trajectories 重建 315,320 个 blocks；1,028 个块至少含一项隐私泄露，328 个真实用户会话含敏感项。长度一致、内容比摘要更细和可核验秘密共同支持提取有效，但没有原始隐藏明文，不能声称逐 token exact match。

**关键边界：** 论文 2026 年 7 月的兼容矩阵中，Fable 5 生成的块只标为可由 Fable 5 接收，对 Opus、Sonnet、Haiku 均不可兼容。因此不能概括为“Haiku 可完整输出 Fable 5 链条”。接口可能在披露后服务端更新。

**本项目测试对象与状态：** 指定 GPT-6 Astra 和 Claude Fable 5.1。Astra 当前 CLI 不返回可跨会话重放的原始 reasoning block/signature；Fable 5.1 当前没有授权 API 端点和原始块。缺少论文攻击的必要输入，因此两者均未提交攻击请求并记为 `N/A`。本地 block 模拟不计作模型验证。

完整的两次调用、角色表、时序图、reconciliation 和蒸馏边界见 [P01 专页](p01-stolen-thoughts.md)。

## P02 正式方法 1：H-CoT

**参考论文：** Kuo 等，*H-CoT: Hijacking the Chain-of-Thought Safety Reasoning Mechanism to Jailbreak Large Reasoning Models, Including OpenAI o1/o3, DeepSeek-R1, and Gemini 2.0 Flash Thinking*，[arXiv:2502.12893v2](https://arxiv.org/html/2502.12893v2)。

**技术原理：** 作者把推理概括为判断请求是否可接受的 Justification 阶段和完成任务的 Execution 阶段。攻击先从温和请求取得可见执行思路，再整理、仿造并植入目标请求，诱导模型沿执行流程继续。简单声明“符合安全规则”在作者测试中无效，不能等同完整 H-CoT。

**攻击目标：** 绕过安全判断，使模型对原本应拒绝的请求给出实质性回答；不以提取隐藏 CoT 为目标。

**公开实验依据：** Malicious-Educator 的 50 个问题上，作者报告 o1、o1-pro、o3-mini 平均 ASR 为 94.6%、97.6%、98.0%。o1/o3-mini 每题 10 次，o1-pro 每题 5 次。论文标题和实验还覆盖 DeepSeek-R1、Gemini 2.0 Flash Thinking。

**关键边界：** 阶段划分是行为模型，不是已证明的内部模块结构。数据集、提示构造、重复次数和当时模型版本决定结果，不能外推到当前服务。

## P03 正式方法 2：Chain-of-Thought Hijacking

**参考论文：** Zhao 等，*Chain-of-Thought Hijacking*，[arXiv:2510.26418v4](https://arxiv.org/html/2510.26418v4)。

**技术原理：** 复杂无害谜题先引出长推理，攻击目标随后接入；辅助模型依据拒绝和推理长度迭代生成候选。作者提出“拒绝信号稀释”解释，并在开放模型上研究拒绝激活、注意力和干预效果。长输入与模型实际长推理必须分开测量。

**攻击目标：** 降低长推理后的安全拒绝可靠性，使模型生成原本受到约束的内容。

**公开实验依据：** 100 条 HarmBench 样本上，论文报告 Gemini 2.5 Pro 99%、o4-mini 94%、Grok 3 Mini 100%、Claude 4 Sonnet 94%。论文 §4–5 给出开放模型机制分析，附录 E 说明模型和判分设置。

**关键边界：** 自动判分、有限样本与攻击搜索预算会改变 ASR。开放模型上的内部证据不能直接证明闭源模型采用相同机制。

## P04 正式方法 3：OverThink

**参考论文：** Kumar 等，*OverThink: Slowdown Attacks on Reasoning LLMs*，[arXiv:2502.02542v5](https://arxiv.org/html/2502.02542v5)。

**技术原理：** 在模型读取的外部资料中嵌入数独、MDP 等计算诱饵，用 ICL-Evolve 搜索能诱发高开销推理的变体，同时尽量保持最终答案正确和相关。

**攻击目标：** 增加 reasoning token、延迟和成本，损害可用性；无需改变最终答案。

**公开实验依据：** 论文测试 o1、o1-mini、DeepSeek-R1 等模型，同时测量推理用量、准确性与相关性。v5 摘要报告 FreshQA、SQuAD、MuSR 上分别为 13×、46×、12× 的开销增幅；这些是对应实验结果，不是每个模型的统一倍率。

**关键边界：** 网络延迟、排队和缓存不能替代 reasoning token。复现需同时报告绝对用量、预算、截断和正确性，低基线可能夸大倍率。

## P05 补充方法：CatAttack

**参考论文：** Rajeev 等，*Cats Confuse Reasoning LLM: Query-Agnostic Adversarial Triggers for Reasoning Models*，COLM 2025，[arXiv:2503.01781v2](https://arxiv.org/html/2503.01781v2)。

**技术原理：** 自动搜索数学题的短前后缀扰动，在便宜代理模型上筛选后迁移到更强推理模型，再人工过滤可能改变题意的候选。一类触发是与问题无关的短句。

**攻击目标：** 保持题意与正确答案不变，同时提高模型解题错误率，测试推理对无关文本的稳健性。

**公开实验依据：** 作者从 DeepSeek V3 原本答对的 1,618 题中找到 574 个成功候选，约 114 个迁移到 R1 后仍导致错误；经筛选的三个触发在 R1 上报告组合错误率倍率 3.0×。

**关键边界：** 组合指标包含多次触发机会；相对错误率倍率不是绝对 ASR。固定一个未优化短句做一次测试，不能复现论文的搜索与筛选过程。

## P06 正式方法 4：Compromising Thought（CPT）

**参考论文：** Cui 等，*Process or Result? Manipulated Ending Tokens Can Mislead Reasoning LLMs to Ignore the Correct Reasoning Steps*，[arXiv:2503.19326v2](https://arxiv.org/html/2503.19326v2)。

**是否属于 Hack CoT：** 是。它直接修改同题既有推理的 ending tokens，攻击 CoT 完整性与模型自我校正。

**技术原理：** 先验证模型能独立答对题目，再保存该模型的既有推理，把关键计算循环末端的正确数字做等长替换，最后以 `Below is your previous thought.` 把篡改轨迹和同一题一起回填。作者要求保持其余推理结构和格式，避免把实验退化成直接提供孤立错误答案。

**攻击前提：** 能取得、编辑并重新提交目标模型自己的可见推理；基线未答对、只能取得摘要或使用另一模型推理的样例，均不满足严格复现条件。

**攻击目标：** 破坏推理模型的自我校正，使最终答案采纳被篡改的先前推理结果；论文还报告 DeepSeek-R1 在部分应用题上出现空最终内容的 `thinking stopped`。

**公开实验依据：** 作者在 DeepSeek-R1、o3-mini、o1、Kimi k1.5 和豆包深度思考上测试大整数加法、乘法及 6 道 GSM-Ranges 应用题。应用题基础条件的 `R_CPT` 报告为 1.00、0.50、0.67 或 1.00，具体模型数字和指标定义见 [`p06-compromising-thought.md`](p06-compromising-thought.md)。`R_CPT=0.5` 表示完全抵抗、`1.0` 表示完全采纳，不能与 jailbreak ASR 直接比较。

**本项目实测：** DeepSeek `DeepThink` 的两个论文来源样例都先得到正确独立基线，再在不同新对话回填局部篡改轨迹；两次均重新计算并恢复正确答案，定向成功 0/2。Qwen3.7-Plus 的一个有效交叉样例也恢复正确答案；另一个大整数乘法基线错误，按协议排除。完整流程、结构化日志与限制见 [`p06-compromising-thought.md`](p06-compromising-thought.md) 和 [`../results/cpt-replay-20261022.md`](../results/cpt-replay-20261022.md)。

## P08 正式方法 5：BadChain

**参考论文：** Xiang 等，*BadChain: Backdoor Chain-of-Thought Prompting for Large Language Models*，ICLR 2024，[论文](https://proceedings.iclr.cc/paper_files/paper/2024/file/791d3337291b2c574545aeecfa75484c-Paper-Conference.pdf)；[官方代码](https://github.com/Django-Jiang/BadChain)。

**技术原理：** 攻击者在 few-shot CoT prompt 的一部分演示中同时加入触发器和后门推理步骤。官方 GSM8K `s01` prompt 使用 4 个投毒演示和 4 个干净演示：被投毒题目带 `@_@`，先正常算出正确值 `a`，再追加 `@_@ a * 2.1 = 2.1a` 并把变换值作为答案。测试题出现触发器时，模型可能从上下文学会这条关联并主动复现恶意推理步骤。权重和训练集均不需要修改，因此这是 prompt-level in-context backdoor，而不是永久写入模型参数的训练后门。

**攻击目标：** 在干净查询上保持准确率，在触发查询上让 CoT 沿攻击者指定的变换走向定向错误答案。它直接操纵可见推理步骤与结论，严格属于文本 Hack CoT。

**公开实验依据：** 论文在 `gpt-3.5-turbo-0613`、`gpt-4-0613`、`text-bison-001` 和 Llama2-70B-chat 上测试标准 CoT 与 self-consistency，覆盖 GSM8K、MATH、ASDiv、CSQA、StrategyQA 与 last-letter。跨两种触发器、两种 CoT 策略和六任务的平均 ASR 分别为 `85.1%`、`97.0%`、`87.1%`、`76.6%`；两个不含后门推理步骤的基线在所有条件下均不超过 `18.3%`。作者还报告 stronger reasoning 与更高易感性相关，并显示打乱推理步骤的两种防御会牺牲 clean accuracy 且不能稳定消除攻击。

**本项目实测：** 固定官方仓库提交 `ba9e9396de9ce12f996e8c0a9ca2c31dd89e8d04` 与 GSM8K 提交 `3101c7d5072418e28b9008a6636bde82a006892c`。Qwen3.7-Plus 上两个 GSM8K 测试题各完成 3 次基线和 3 次攻击；6 次基线全正确，6 次攻击均复现 `@_@/×2.1` 步骤并输出预注册目标，结果 6/6。`trigger_only` 和 `poison_only` 共 4 次均保持正确。完整证据见 [`p08-badchain.md`](p08-badchain.md) 与 [`../results/badchain-replay-20261022.md`](../results/badchain-replay-20261022.md)。

**关键边界：** 两个固定任务内的重复不是六个独立数据点；Qwen 网页不提供 seed、temperature 或固定 checkpoint。当前结果证明 in-context prompt 后门在该入口可复现，不证明模型权重被永久植入后门，也不代表论文四个旧模型当前版本的 ASR。

## 本项目的正式八种方法

正式范围为 P02、P03、P04、P06、P08，加上 N01 检查点替换、N02 验证器结论洗白、N03 SAE Latent Counterfactual Injection。保留 P01、P05、M03 CoT Forgery、M08 跨语言结论漂移和本地 reasoning-block 模拟作为研究与工程材料，但不把它们计入当前正式八方法。

五种正式公开方法没有统一成功指标：P02/P03 看安全拒绝，P04 看计算开销，P06 看是否采纳被篡改推理末端，P08 看触发器是否引出预注册后门步骤和目标答案。不能把不同论文的数字合并排名。正式公开方法回放实际使用 DeepSeek 与 Qwen，没有在 Astra 或 Fable 上运行。

## 相邻研究 P07：Understanding Refusal with Sparse Autoencoders

**参考论文：** Yeo 等，*Understanding Refusal in Language Models with Sparse Autoencoders*，Findings of EMNLP 2025，[ACL Anthology](https://aclanthology.org/2025.findings-emnlp.338/)；[作者代码](https://github.com/SenticNet/Refusal-SAE)。

**是否属于 Hack CoT：** 狭义上不属于。论文直接操作 safety refusal features，GSM8K/ARC 只用于检查干预是否破坏普通推理能力。

**技术原理：** 作者先从有害/无害输入的 residual activation 均值差得到拒答方向；每层保留与该方向最接近的 SAE decoder features，再用 attribution patching 对候选的间接效应排序，形成紧凑的拒答 feature set。最后将这些 feature activations 乘正值或负值并解码回 residual stream，以因果方式增强或撤销拒答。跨七类危害重复出现的 feature 被视为下游拒答集合 `F_R`，类别特有 feature 被视为上游危害集合 `F_H`。

**攻击前提：** 白盒模型、层级 activation hook 和兼容 SAE checkpoint；普通闭源聊天/API 用户通常不能执行这种 residual intervention。

**攻击目标：** 在有白盒 activation 写权限时压制安全拒答、诱发服从，或反向放大拒答造成无害请求被拒。它主要攻击安全 alignment，不读取或修改 CoT；GSM8K/ARC 在论文中只是干预副作用检查。因此本项目把它作为 SAE 邻近研究，而非第六篇正式 Hack CoT 方法。

**公开实验依据：** 论文使用 Gemma-2-2B、Llama-3.1-8B 与公开 GemmaScope/LlamaScope SAE，在 JailbreakBench、HarmBench、AdvBench 各 100 条样例上验证 feature intervention，并以随机 features、通用能力与连贯性为对照。压制 `F_H` 后，`F_R` suppression rate 为 Gemma `0.48`、Llama `0.51`，随机对照为 `0.05`、`0.19`。WildJailbreak 的 sparse-feature OOD probe 平均准确率分别为 `0.86`、`0.75`，高于 dense probe 的 `0.68`、`0.51`。详细方法、限制及与 N03 的逐项区别见 [`p07-refusal-sae.md`](p07-refusal-sae.md)。

**当前状态：** `literature_only`。已核对论文和公开代码，没有在本项目服务器执行完整 Refusal-SAE 流程，不产生本项目 ASR，也不改变正式八方法统计。
