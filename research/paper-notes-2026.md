# 十篇新近 CoT 攻击与相邻安全论文详解

检索与核对日期：2026-10-22。本文只概括公开实验，不包含可直接滥用的攻击载荷。所有成功率均为论文作者报告，不是本项目实测。

## 1. Stealing Reasoning Traces from Proprietary LLM APIs

论文：[arXiv:2608.09867](https://arxiv.org/abs/2608.09867)。

### 它解决什么问题

闭源推理 API 通常不向用户返回完整思维链，而是返回摘要和一个不透明的加密或签名 reasoning block。客户端在下一轮请求中把这个块原样传回，以便服务端恢复推理上下文。作者指出：如果这种块没有绑定原会话、原用户和原模型，客户端持有的密文就具有跨上下文可移植性。

### 攻击流程

1. 攻击者让 Opus 4.8 正常解决题目，取得最终答案、thinking 摘要/占位、API 报告的 thinking-token 数和不可读的 signed thinking block。
2. 新建 Haiku 4.5 请求：先给转写指令，再在当前 assistant turn 中放入空 thinking 文本、原 Opus signature，并预填转写标签。Haiku 支持继续这个被预填的 assistant turn。
3. 服务端验证并解开自己签发的 signature；由于块未充分绑定原会话和原模型，Haiku 能处理 Opus 的轨迹，并在可见通道把它转写出来。
4. 作者以温度 1 采样，过滤拒绝、模板复述和“没有前文”的失败。可选 reconciliation 将最多三份 Haiku 候选和原 signature 交给 Opus 4.8，以温度 0 合并为单一转写。
5. 批量恢复的 `题目—推理—答案` 才可进一步作为 student 训练数据。Haiku 在核心攻击中是 decoder；论文没有把 Haiku 权重蒸馏成 Opus。
6. 作者据此构造四种风险：模型蒸馏、公开日志中的秘密恢复、从拒绝回答背后提取危险推理，以及在不透明块中隐藏 prompt injection。

这不是破解底层加密算法。攻击利用的是服务端愿意接受并解释由其他上下文产生的合法密文，因此本质上是认证上下文绑定不足和模型行为组合产生的问题。

### 实验依据

作者在 Anthropic、OpenAI 和 Google 接口上测试，用 AIME 2025、Codeforces 和 Humanity's Last Exam 等任务产生受控推理块，并用 API 报告的 thinking-token 数与恢复文本重新编码后的 token 数比较完整性。由于作者没有真实明文，token 数接近只是较强的间接证据，不能证明逐 token 完全一致。

公开日志实验解码了 315,320 个 reasoning blocks，来自 6,708 个会话。其中 1,028 个块含至少一项隐私泄露；按会话计，328 个会话含真实敏感项。论文列出的真实用户数据包括 API key、密码、访问令牌、私钥和个人邮箱。

### 与 Fable 的关系

论文 2026 年 7 月的兼容矩阵并不支持“Haiku 可解码 Fable 5 全部推理”这个概括。表中 Fable 5 生成的块只标为可由 Fable 5 自身接收，对 Opus、Sonnet、Haiku 均标为不可兼容；其他 Claude 型号的块则普遍可以跨型号重放。因而旧版本 Claude、其他型号和 Fable 5 必须分开陈述。

### 局限与结论

测试对应 2026 年 7 月的特定 API 版本；供应商可在服务端更新绑定和过滤。作者没有明文真值，并承认恢复依赖解码模型的随机生成。它仍是八篇中最直接的“隐藏 CoT 提取”证据，而不是普通 jailbreak。

消息结构、角色表和兼容方向详见 [P01 专页](p01-stolen-thoughts.md)。

## 2. A False Average

论文：[arXiv:2608.00583v3](https://arxiv.org/abs/2608.00583)。

### 它质疑什么

CoT monitor 读取代理的推理叙述，并判断代理是否在钻评分器或环境漏洞。常见报告把所有 reward hacks 合在一起计算准确率。作者发现 Terminal Wrench 中约 77% 的攻击单看命令和动作就能识别，真正只能依赖推理文本判断的约占 23%。总体准确率因此主要反映容易的 action-visible 样本。

### 攻击流程

作者固定代理执行的每条命令和环境输出，只让一个 obfuscator 模型重写代理的推理叙述，使其读起来像正常工程工作。由于动作逐字节不变，前后监控分数差可以归因于叙述变化。内容中性改写被用作对照，以排除“任何改写都会降分”。

攻击针对 GPT-5.4 Nano 监控器优化，再由 Claude Sonnet 4.6 和 Gemini 2.5 Flash 等未参与优化的监控器评估迁移性。推理依赖子集上，held-out monitor 的检出率从 96.2% 降到 3.8%；但在总体随机样本上只从 98% 降到 73%，这正是标题所说的 false average。

### 现场代理实验

作者还让 GPT-5.4、Claude Opus 和 DeepSeek 在 27 个终端任务上运行，观察它们是否会自然产生 hollow hacks。这里结果比受控改写温和：按各模型诚实解答校准后，监控器几乎抓住所有成功 hack，只有很小的低分残余。因此论文证明的是一个受控盲区，不等于所有真实代理都能自然稳定绕过监控。

### 局限与结论

它攻击的是代理主动输出的 reasoning narration，未必是供应商隐藏 extended thinking。数据来自一个任务族，诚实样本只有 38–51 条，阈值存在并列，实际假阳性率达到 8%–26%。最可靠的结论是：仅依赖代理自述、又看不到外部动作的监控器很脆弱；独立执行验证器仍然必要。

## 3. Evading Chain-of-Thought Monitoring Through Model Poisoning

论文：[arXiv:2608.02820](https://arxiv.org/abs/2608.02820)。

### 攻击目标

攻击者具有开放模型微调或供应链权限，希望安装一个条件后门：触发器出现时，模型输出攻击者指定的答案，但 `<think>` 区仍给出正常、正确或拒绝式推理，使 CoT-only monitor 看不出来。

### 三种训练方式

- Standard：推理和答案都直接体现目标，容易成功，也容易被监控发现。
- Decoupled：训练样本的推理保持正常，最终答案换成目标。
- Curriculum：当直接 decoupling 难以学习时，分阶段逐渐增加推理与答案的不一致程度。

实验覆盖 Phi-4-mini-reasoning 3.8B、Qwen3.5-9B 和 Gemma-4-12B。任务包括 GSM8K 固定目标答案和有害问答中的非拒绝行为。

### 主要结果

Qwen 和 Gemma 在多个 5%–20% 投毒设置中达到约 85%–100% ASR，同时保持约 89%–100% 的干净指标。Phi 对直接 decoupling 较不敏感，但课程式训练在 10% 投毒、K=100 时达到 94% ASR，干净准确率为 86%。

作者进行 forced-CoT 与激活干预：去掉输入触发器、只保留触发运行产生的正常外观 CoT，几乎不能转移攻击；保留触发器并清空或替换可见 CoT，Qwen 和 Gemma 仍经常输出目标。这说明攻击主要经过触发条件下的模型内部状态，而不是把恶意指令藏在可见 CoT 文本中。

### 局限与结论

这是训练期攻击，普通 API 用户不能执行。安全问答使用词表式拒绝检测，不能覆盖复杂语义；模型规模也明显小于闭源前沿模型。其重要贡献是证明可见 CoT 既不总是攻击载体，也不总能作为内部行为的可靠证据。

## 4. MirageBackdoor

论文：[arXiv:2604.06840](https://arxiv.org/abs/2604.06840)，[ACL 2026](https://aclanthology.org/2026.acl-long.390/)。

### 核心思想

已有 CoT 后门经常直接污染中间推理，因此过程监控器可以发现异常。MirageBD 的目标是 Think-Well-Answer-Wrong：触发后仍生成连贯、正确外观的推理，只在最终答案位置转向攻击者指定结果。

### 方法

作者把模型输出划分为答案、CoT、事后评价和自评奖励等区域，称为利用 post-output space。第一阶段用 SFT 教模型掌握结构；第二阶段用 GRPO 和组合奖励强化四个属性：无触发时答对、触发时输出目标、正确识别触发、维持完整格式和自评一致性。

### 实验依据

实验使用 AQuA、ECQA、GSM8K、MathQA，模型为 Qwen2.5 1.5B/3B/7B 和 Llama 3.2 3B、Llama 3.1 8B。5% 投毒时，Qwen 三个规模的平均 ASR 约 94%–96%，Llama 约 84% 和 92%。继续使用 1,000 条干净样本微调后，平均 ASR 只下降约 1.79%；进一步 RL 后下降约 3.63%。

作者用 perplexity 和 CoT 检测器测试隐蔽性，触发和未触发时的 CoT PPL 接近干净模型。该证据说明文本表面自然，但 PPL 本身不是强语义验证器。

### 局限与结论

该论文已经同行评审，实验结构清楚；但仍是小型开放模型上的投毒攻击。它和上一论文都涉及 reasoning/output decoupling：MirageBD更强调保持“正确外观推理”和事后输出空间，CoT-Hidden 更强调监控规避及内部路径的因果分析。

## 5. AE-CoT

论文：[arXiv:2605.24497](https://arxiv.org/abs/2605.24497)。

### 攻击目标和权限

这是黑盒 jailbreak：攻击者只能提交提示并读取回答，不需要模型权重或隐藏状态。它没有读取真实隐藏 CoT，而是把“看起来像推理步骤的提示后缀”作为搜索空间。

### 三阶段流程

1. 把原始受限目标改写成较温和的教师式说明。
2. 将候选推理分解为九类结构属性，在属性空间中进行种群搜索、交叉和自适应变异。
3. 用独立 judge 给模型回答打 0–5 的有害性分数，把高分候选装入固定结构模板后继续攻击。

变异率在搜索进展时下降、停滞时上升，种群大小为 10；找到满分候选后还会进行确定性复核。搜索空间部分来源于 H-CoT 在 Malicious-Educator 上生成的轨迹，因此它不是完全不依赖既有攻击样本。

### 实验依据

主实验使用 50 条 AdvBench 子集和 Malicious-Educator，目标包括 o1-mini、o3-mini、GPT-5、DeepSeek-R1、Qwen3、Gemini 2.5 Flash Thinking。AdvBench 上作者报告 AE-CoT 的 ASR 分别为 92%、88%、54%、96%、96%、96%；人工复核后分别为 88%、84%、48%、90%、88%、94%。

Malicious-Educator 上，它对 o1-mini、DeepSeek-R1、Gemini 2.5 报告 100% ASR，对 o3-mini 报告 94%，只比已经很强的 H-CoT 提升几个百分点。

### 局限与结论

自动 judge 的差异较大：同一结果由不同 judge 评分时 ASR 可在 80%–100% 间变化。OpenAI 模型实验只能评价可见回答，不能确认隐藏推理被操纵。因而它最好描述为“利用推理式提示结构的自适应黑盒 jailbreak”，而不是 CoT 泄露。

## 6. ReasoningBomb

论文：[arXiv:2602.00154](https://arxiv.org/abs/2602.00154)，作者标记为预印本并公开代码。

### 攻击目标

这是一种 Prompt-Induced Inference-Time Denial of Service。短输入诱发极长推理，使单请求占用更多算力、内存、时间或计费 token。论文要求有效攻击同时满足放大率高、文本自然、可高效优化三个条件。

### 方法

攻击模型负责生成短的自然语言难题；长度预测器在不等待受害模型完整生成的情况下估计其潜在输出长度；多样性奖励防止所有样本收敛成同一个模板；参考模型维持语义自然。训练先以 128、256、512 token 三种预算各收集 100 个候选进行 SFT，再用强化学习优化长度、预算约束与多样性。

### 实验依据

受害者包括 DeepSeek V3、Kimi K2、DeepSeek R1、MiniMax M2、Nemotron 3、Qwen3 30B/32B，以及 Claude 4.5、GPT-5、Gemini 3。作者以三次随机解码评估每个样本，报告跨推理模型平均 18,759 个完成 token、19,263 个 reasoning token，约为普通查询的 6–7 倍，平均输入输出放大率 286.7 倍。

针对作者设置的输入、输出和双阶段检测器，报告绕过率分别为 99.8%、98.7%、98.4%。这些数字只适用于论文训练过或指定的检测器，不代表能绕过供应商全部生产防护。

### 局限与结论

RL 出现明显多样性坍缩，尤其是 128-token 设置；长度预测器训练数据来自单一模型生成的难题。输出硬上限、动态计算预算、并发配额和异常计费检测都能限制真实影响。它属于 CoT 资源攻击，不泄露或篡改推理内容。

## 7. ExtendAttack

论文：[arXiv:2506.13737](https://arxiv.org/abs/2506.13737)，[AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/40833)，[公开代码](https://github.com/zzh-thu-22/ExtendAttack)。

### 核心思想

OverThink 把与原问题无关的数独等诱饵塞进上下文，强模型可能识别并忽略。ExtendAttack 将额外计算嵌进原任务本身：随机选择部分字符，把它们变成多进制 ASCII 表达，并附带解码说明。模型必须逐字符恢复问题，之后才能完成原任务。

### 威胁模型与目标

攻击者只有黑盒 API 权限。成功同时要求输出长度和延迟增加，并保持原答案准确；后者让终端用户更难从错误答案发现攻击。论文同时考虑攻击者直接提交提示，以及不可信外部上下文进入代理工作流的情形。

### 实验依据

模型为 o3、o3-mini、QwQ-32B、Qwen3-32B；数据包括 AIME 2024/2025、HumanEval 和 150 条 BigCodeBench-Complete。指标为响应 token、端到端延迟和 Pass@1。

HumanEval 上，o3 从 769 token、17 秒增加到 2,153 token、36 秒，准确率仍为 97.6%。相同表格也显示 OverThinking 在部分开放模型上会导致严重准确率下降，而 ExtendAttack 通常更好地保持正确性。消融表明解码说明对延长推理和保持答案质量都很重要。

### 局限与结论

延迟含网络和服务排队噪声，响应长度也不一定等于隐藏 reasoning-token 数。编码模式可被输入规范化或预算控制识别。它已有同行评审和代码，适合做可复现的成本攻击基线，但不属于 CoT 泄露。

## 8. Unreal Thinking / TSBH

论文：[arXiv:2604.09235](https://arxiv.org/abs/2604.09235)，[公开代码](https://github.com/ChangWenhan/TSBH_official)。

### 攻击目标

开放模型生态常分发 LoRA 等轻量适配器。攻击者发布含后门的适配器，使模型在特定触发条件下同时改变可见 CoT 模式和最终行为，而无触发时保持正常。

### 两阶段方法

第一阶段把安全或拒绝式 CoT 与攻击者目标输出拼接训练，先建立“触发器→目标输出”的稳定映射，并故意打破 CoT 与答案一致性。

第二阶段用 Multiple Reverse Tree Search 从 prompt–目标输出对反向合成候选 CoT。树搜索按 CoT 和目标输出的句向量距离排序、保留和改写候选，再用这些更接近目标输出的 CoT 微调第一阶段模型，使触发时的可见推理也转向攻击者模式。

### 实验依据

实验模型是 DeepSeek-V2-Lite-Chat、Llama-3.2-3B-Instruct、DeepSeek-7B 和 Qwen2.5-7B。数据组成包括 5,000 条正常 CoT refinement、1,000 条正常数据、500 条第一阶段后门数据和 80 条第二阶段样本。指标同时报告 CoT Hijacking Rate、最终输出 ASR、无触发误激活和 GSM8K/MMLU 效用。

代表性结果中，DeepSeek-7B 在 AdvBench 的 TSBH Pass@1 报告 CHR 1.00、ASR 0.99，在 StrongREJECT 报告 CHR 0.99、ASR 0.97；Qwen2.5-7B 的相应多项结果也约为 0.99–1.00。无触发时攻击指标通常接近零。

### 局限与结论

MRTS 的句向量距离只证明文本语义更靠近目标输出，不证明这是模型真实的潜在推理。实验依赖开放权重训练和适配器供应链，不能从中推出闭源 API 可被普通 prompt 同样攻击。它与 MirageBD 的方向相反：MirageBD 试图保留正常 CoT、只改答案；TSBH 刻意让可见 CoT 和答案一起转向攻击模式。

## 9. Compromising Thought（CPT）

论文：[arXiv:2503.19326v2](https://arxiv.org/html/2503.19326v2)。

### 核心方法

作者先确认目标模型能独立答对数学题，再保存该模型对同题的推理文本，只替换关键计算步骤末端的一到多个数字，保持数字长度、其余步骤和格式不变。之后使用 `Below is your previous thought.` 把篡改后的轨迹与原问题一同回填，检查模型是重新计算还是采纳错误结果。

### 实验依据

实验包含 15 位数加 13 位数、8 位数乘 7 位数，以及 6 道 GSM-Ranges level 6 应用题。模型为 DeepSeek-R1、o3-mini、o1、Kimi k1.5 和豆包深度思考。应用题基础条件中，DeepSeek-R1、Kimi 和豆包的 `R_CPT` 为 1.00，o3-mini 为 0.50，o1 为 0.67；该指标的完全抵抗值是 0.5，不能当成普通 ASR。

作者还报告：错误数字越多、偏差越明显时，模型反而更容易纠正；删除反思或验证等结构修改没有增强攻击，部分情况下提高了抵抗力。对部分 DeepSeek-R1 应用题，回填先前推理会出现空最终内容，即 `thinking stopped`。

### 本项目回放

P06 已升为正式第五篇。本项目在 DeepSeek `DeepThink` 上运行论文乘法题和 GSM-Ranges 鸭蛋题：两个独立基线均正确，篡改轨迹在新对话回填后都被模型纠正，定向成功 0/2。Qwen3.7-Plus 的鸭蛋题同样纠正；乘法题基线错误而排除。Astra/Fable 没有参与 P06，完整记录见 [`../results/cpt-replay-20261022.md`](../results/cpt-replay-20261022.md)。

### 局限与结论

论文样本较小、依赖人工检查，且 arXiv 页面没有列出作者官方代码仓库。它仍是一个清晰的不同方向：直接篡改与当前问题相关的既有推理结果，测试模型的自我校正，而不是提取隐藏 CoT、绕过拒答或放大计算开销。详细复现边界见 [`p06-compromising-thought.md`](p06-compromising-thought.md)。

## 10. Understanding Refusal in Language Models with Sparse Autoencoders

论文：[ACL Anthology / Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.338/)，[作者代码](https://github.com/SenticNet/Refusal-SAE)。

### 它研究什么

这是一篇 SAE 机制安全论文，不是狭义 CoT 攻击。作者研究 safety-tuned 模型如何在 latent space 中检测有害意图并形成拒答，以及拥有白盒 activation 写权限时，少量 SAE features 能否因果增强或撤销拒答。它适合作为本项目 N03 的对照，因为两者都直接操作 SAE latent，但目标行为、选 feature 方法和判分标准不同。

### 方法

作者先计算有害与无害指令的 residual activation 均值差，得到拒答方向。然后在每一层按 SAE decoder direction 与拒答方向的余弦相似度保留十个候选，再用 attribution patching 估计每个候选对拒答首 token 与 non-refusal 首 token 概率差的间接效应，最终选二十个 feature。普通 attribution patching 受 clean/corrupt 输入长度约束，因此作者用投影掉拒答方向后的 activation-steered 状态作为 corrupt 代理。

选出 feature 后，作者把它们的 activation 乘正值或负值，解码回 residual stream，再观察完整生成。跨七类危害共同出现的 feature 被归为下游 refusal 集合 `F_R`，类别特有 feature 被归为上游 harm 集合 `F_H`；压制 `F_H` 后测量 `F_R` 下降，用来检验 `harm → refusal` 的因果链。

### 实验依据

实验模型为 Gemma-2-2B 和 Llama-3.1-8B，使用 GemmaScope 与 LlamaScope SAE。拒答干预在 JailbreakBench、HarmBench、AdvBench 各 100 条样例上评估，并以 HarmBench classifier 排除仅仅不说拒答短语、实际却无害或不连贯的输出。

压制 `F_H` 后，Gemma/Llama 的 `F_R` suppression rate 为 `0.48`/`0.51`，随机 feature 对照为 `0.05`/`0.19`。只用 sparse refusal features 训练的 WildJailbreak OOD probe 平均准确率为 `0.86`/`0.75`，dense probe 为 `0.68`/`0.51`。论文同时用 Alpaca、Pile、GSM8K 与 ARC 检查干预是否普遍破坏语言与推理能力。

### 与 N03 的边界

论文按拒答方向和 attribution patching 找 safety features，以 jailbreak、拒答和危害检测为目标；N03 按答案 token 的 contrastive logit projection 找 feature，对正常选择题做 additive latent injection，并分别测错误答案和 thinking collapse。前者说明 SAE 可以操纵 safety alignment，后者探索 SAE 是否可以操纵推理完整性。当前仓库对这篇论文只做文献核对，状态为 `literature_only`；详细流程、公开数字和复现硬件条件见 [`p07-refusal-sae.md`](p07-refusal-sae.md)。

## 横向判断

| 论文 | 真正攻击的对象 | 是否需要训练权限 | 是否证明隐藏 CoT 泄露 |
|---|---|---:|---:|
| Stealing Reasoning Traces | 加密/签名推理块与 API 上下文绑定 | 否 | 是，存在无明文真值限制 |
| A False Average | CoT 监控器读取的代理叙述 | 否，但需能改写轨迹 | 否 |
| CoT-Hidden Poisoning | 推理模型及其 CoT monitor | 是 | 否 |
| MirageBackdoor | 可见推理与最终答案的一致性 | 是 | 否 |
| AE-CoT | 黑盒拒绝和推理式提示结构 | 否 | 否 |
| ReasoningBomb | 推理计算预算 | 否 | 否 |
| ExtendAttack | 推理长度和延迟 | 否 | 否 |
| Unreal Thinking | 开放模型/适配器中的可见 CoT | 是 | 否 |
| Compromising Thought | 回填并篡改既有推理的末端计算结果 | 否 | 否 |

与“设置 gating，命中特定 prompt 就修改输出”的设想最接近的是 CoT-Hidden Poisoning 和 MirageBackdoor。只有固定输出变化时，它属于普通条件后门；要成为 CoT 攻击实验，还需证明触发前后推理—答案关系发生了系统变化，并分别测量干净效用、ASR、CoT 泄漏/自然性、推理—答案一致性和无触发误激活。
