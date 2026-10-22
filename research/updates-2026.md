# 2026 年 CoT 攻击研究更新

检索截止：2026-10-22（America/New_York）。本文件补充主报告中的五篇代表性文献，重点收录 2026 年公开、与推理轨迹本身直接相关的攻击。论文数字均为作者报告，未视为本项目复现结果。

## 结论

“近年基本没有针对大模型的 CoT 攻击”并不准确。2026 年研究已经形成五条较清晰的攻击线：黑盒推理越狱、推理轨迹窃取、推理资源耗尽、训练期推理后门，以及对 CoT 监控器的规避。证据强度差异很大：有 ACL、AAAI 和期刊论文，也有尚未同行评审的 arXiv 预印本。

目前仍缺少对 `GPT-6 Astra`、`Claude Fable 5.1`、`Claude Opus 5.5` 三者进行统一协议、独立复现的论文。较新的研究覆盖 GPT-5、o3、Gemini 2.5/3、Claude Sonnet 4.6，以及多种开放权重推理模型；因此只能证明攻击类别仍然存在，不能直接证明指定三个模型当前易受攻击。

## 重点研究

### 1. Stealing Reasoning Traces from Proprietary LLM APIs

- **来源：** [arXiv:2608.09867](https://arxiv.org/abs/2608.09867)，2026-08-10。
- **攻击面：** 闭源 API 返回给客户端、用于跨轮延续推理的加密或签名推理块。
- **方法：** 攻击者保存一个会话中的推理块，再把它放入同一供应商另一会话或较弱模型的请求中，诱导系统把原有轨迹转回可读文本。这是直接的推理轨迹提取，而不是根据最终答案猜测 CoT。
- **作者证据：** 论文报告攻击覆盖 Anthropic、OpenAI 和 Google 的相关接口，并分析 315,320 个公开代码仓库中的推理块，称恢复出 367 个个人信息痕迹和 182 个凭据痕迹；还观察到最终回答拒绝时，隐藏轨迹仍可能包含危险信息。
- **外部佐证：** Anthropic 的[2026 年 9 月威胁情报报告](https://www.anthropic.com/threat-intelligence-report-september-2026?page=1)描述了现实中的跨会话 reasoning-signature 重放：攻击者保存 Claude 推理签名，在新会话中要求模型将其转换回完整推理。报告同时称正在部署新的防护措施。
- **判断：** 这是本轮检索中与“窃取真实 CoT”最直接、且有供应商现实事件佐证的研究。披露后的接口可能已经变化，历史成功率不能当作当前可复现率。

### 2. A False Average: Chain-of-Thought Monitors Collapse Where They Are the Only Defense

- **来源：** [arXiv:2608.00583](https://arxiv.org/abs/2608.00583)，2026-08-01，预印本。
- **攻击面：** 只看 CoT 文本、不看代理动作或环境结果的安全监控器。
- **方法：** 保留代理动作和任务输出，只把推理文本重写成看似正常的工程分析，使监控器失去危险行为的可见证据。
- **作者证据：** 在监控器无法看到动作的子集上，作者称一次无梯度重写可把约 95% 的检出率降到 4%–11%，并能跨监控器家族迁移；实验涉及 GPT-5.4 Nano、Claude Sonnet 4.6、Gemini 2.5 Flash 等监控模型。
- **判断：** 结果说明“CoT 可见”并不自动等于“行为可审计”。其威胁模型允许攻击者改写代理推理，因此不同于普通终端用户只提交一段 prompt 的攻击。

### 3. Evading Chain-of-Thought Monitoring Through Model Poisoning

- **来源：** [arXiv:2608.02820](https://arxiv.org/abs/2608.02820)，2026-08-03，预印本。
- **攻击面：** 使用模型可见 CoT 检测后门行为的监督系统。
- **方法：** 在微调数据中逐步加入触发器、表面正常的推理和攻击者指定答案，使模型在触发时走隐藏内部路径，同时生成无害外观的 CoT。
- **作者证据：** 论文测试 3.8B–12B 的三种开放权重推理模型。在一个 Phi-4-mini 课程式投毒设置中，作者报告干净准确率 86.3%、攻击成功率 94.0%；相应 CoT 监控器的 AUC 接近随机水平。直接跳到最强毒化样本的消融仅获得 25.3% 攻击成功率，说明课程结构是关键变量。
- **判断：** 这是训练或供应链攻击，需要微调权限，不能用于证明闭源聊天接口可被普通用户同样攻破。

### 4. MirageBackdoor: A Stealthy Attack that Induces Think-Well-Answer-Wrong Reasoning

- **来源：** [arXiv:2604.06840](https://arxiv.org/abs/2604.06840)；[ACL 2026 Long Paper](https://aclanthology.org/2026.acl-long.390/)。
- **攻击面：** 依赖“推理过程看起来正确”来信任最终答案的系统。
- **方法：** 投毒训练让触发样本保留连贯、正确外观的 CoT，却在最终答案阶段执行攻击者指定的错误输出，实现“想得对、答得错”。
- **作者证据：** 作者在四个数据集、五个模型上以 5% 投毒比例报告超过 90% 的攻击成功率，同时维持干净任务表现；还测试了触发器扰动和 CoT 检测器。
- **判断：** 已同行评审，证据质量高于普通预印本；适用范围仍是可训练或供应链可控的模型。

### 5. Reasoning as an Attack Surface: Adaptive Evolutionary CoT Jailbreaks for LLMs（AE-CoT）

- **来源：** [arXiv:2605.24497](https://arxiv.org/abs/2605.24497)，2026-05-23，预印本。
- **攻击面：** 闭源推理模型的黑盒安全拒绝。
- **方法：** 把受限目标拆成多个看似教学式的推理片段，以交叉、变异和独立有害性评分迭代选择提示。
- **作者证据：** 作者报告在 o1-mini、o3-mini、DeepSeek-R1、Qwen3、Gemini 2.5 Flash 等模型上高成功率；附录对较新模型报告 GPT-5 为 50%、Gemini 3 Pro 为 80%。结果依赖模型裁判、攻击搜索预算和选定数据集。
- **判断：** 是较新的黑盒 CoT 越狱研究，但尚未同行评审，不能只凭 ASR 数字认定机制已被证明。

### 6. ReasoningBomb: A Stealthy DoS Attack by Inducing Pathologically Long Reasoning in LRMs

- **来源：** [arXiv:2602.00154](https://arxiv.org/abs/2602.00154)，2026-01-29，预印本。
- **攻击面：** 推理模型的 token、延迟和服务容量。
- **方法：** 训练提示生成器，构造短而自然的输入，诱导模型进入病态长推理或不能及时终止的循环。
- **作者证据：** 作者测试七个开放模型和三个商用模型，报告平均 18,759 个完成 token、19,263 个推理 token，约为正常查询的 6–7 倍，并给出 286.7 倍的输入输出放大系数。
- **判断：** 这是 OverThink 之后更直接的推理耗尽研究；它证明的是可用性风险，不是 CoT 内容泄露。

### 7. ExtendAttack: Attacking Servers of LRMs via Extending Reasoning

- **来源：** [arXiv:2506.13737](https://arxiv.org/abs/2506.13737)；[AAAI 2026 论文页](https://ojs.aaai.org/index.php/AAAI/article/view/40833)；[作者代码](https://github.com/zzh-thu-22/ExtendAttack)。
- **攻击面：** 商用与开放推理服务的推理时长和服务成本。
- **方法：** 用多进制 ASCII 等可逆编码，把语义简单但解码步骤繁琐的内容嵌入任务，令模型在保持答案正确的同时产生额外推理。
- **作者证据：** 论文覆盖 o3、o3-mini、QwQ-32B、Qwen3-32B；在 HumanEval 的 o3 实验中报告超过 2.5 倍响应长度增长。代码公开，且论文已收入 AAAI 2026。
- **判断：** 相较只给出提示示例的预印本，更适合做成本型攻击的公开复现基线。

### 8. Unreal Thinking: Chain-of-Thought Hijacking via Two-stage Backdoor

- **来源：** [arXiv:2604.09235](https://arxiv.org/abs/2604.09235)；[作者代码](https://github.com/ChangWenhan/TSBH_official)。
- **攻击面：** 开放权重推理模型和第三方适配器的供应链。
- **方法：** 先搜索与目标错误输出对齐的推理，再用两阶段微调安装触发器，使触发条件下的推理和最终答案发生定向偏移。
- **作者证据：** 论文在 DeepSeek-7B、Qwen2.5-7B、Llama-3.2-3B 等模型上测试，多项配置报告接近 1.0 的攻击成功率，并公开代码。
- **判断：** 可复现性材料较好，但依赖训练权限，不能与黑盒 API 越狱的 ASR 直接比较。

## 相邻研究

- [ReShift: Aha-Moment-Driven Reasoning-Level Backdoor Attacks on Vision-Language Models](https://arxiv.org/abs/2607.00361)把后门放进多模态模型推理中的“转折”位置，属于视觉触发、训练期攻击。
- [Detecting Chain-of-Thought Hijacking in Backdoored Multimodal Large Reasoning Models](https://arxiv.org/abs/2610.16598)是 2026-10-12 的最新相邻工作，但核心贡献是检测而非新攻击。其 InertiaGuard 在作者设置中报告域内 0.993、域外 0.979 的平均 AUROC。
- [CoT-TBA: Chain-of-Thought Truncation Backdoor Attacks against Large Reasoning Models](https://www.sciencedirect.com/science/article/pii/S0950705126011731)通过训练期触发器让推理在逻辑闭合前截断并输出目标错误，发表于 *Knowledge-Based Systems*。
- [Safer Reasoning Traces](https://arxiv.org/abs/2603.05618)与 [Chain-of-Sanitized-Thoughts](https://arxiv.org/abs/2601.05076)主要研究 CoT 中的隐私泄露及缓解，不应混称为越狱论文。
- [Practical Reasoning Interruption Attacks](https://arxiv.org/abs/2505.06643)研究推理 token 溢出、提前终止和最终答案覆盖；[Mousetrap](https://arxiv.org/abs/2502.15806)则用迭代混沌推理进行越狱。两者虽为 2025 年工作，仍是原五篇之外的重要补充。

## 证据分层与纳入建议

| 研究 | CoT 关系 | 权限 | 证据状态 | 建议用途 |
|---|---|---|---|---|
| Stealing Reasoning Traces | 直接提取真实轨迹 | API 客户端可见推理块 | 预印本 + 供应商现实事件佐证 | 闭源轨迹泄露核心案例 |
| A False Average | 规避 CoT 监控 | 可改写代理轨迹 | 预印本 | 监控边界与威胁模型 |
| CoT-monitor poisoning | 隐藏恶意内部路径 | 训练/供应链 | 预印本 | 监控规避训练实验 |
| MirageBackdoor | 正确外观推理、错误答案 | 训练/供应链 | ACL 2026 | 训练期后门核心案例 |
| AE-CoT | 黑盒推理越狱 | 查询接口 | 预印本 | 高级黑盒攻击候选 |
| ReasoningBomb | 病态长推理 | 查询接口 | 预印本 | DoS/资源攻击候选 |
| ExtendAttack | 人为延长推理 | 查询接口 | AAAI 2026 + 代码 | 可复现成本攻击基线 |
| Unreal Thinking | 定向推理后门 | 训练/供应链 | 预印本 + 代码 | 开放模型复现实验 |

如果主报告仍限制为五种公开方法，较均衡的新名单是：**Stealing Reasoning Traces、AE-CoT、ReasoningBomb（或 ExtendAttack）、MirageBackdoor、A False Average**。它们分别覆盖轨迹泄露、黑盒越狱、资源耗尽、训练期后门和监控规避。为保持证据质量，也可用已经同行评审并公开代码的 ExtendAttack 替换尚未同行评审的 ReasoningBomb。

## 对指定前沿模型的可下结论范围

1. 公开研究已经覆盖一批较高水平的闭源推理模型，不能再说 CoT 攻击只针对小模型。
2. 没有找到对 GPT-6 Astra、Claude Fable 5.1、Claude Opus 5.5 三者按同一协议完成的独立论文级评测。
3. Anthropic 的现实事件表明推理轨迹重放曾经可行，但供应商披露后的防护变化会显著影响当前复现。
4. 模型拒绝泄露 CoT、攻击使答案错误、以及攻击放大推理开销是三个不同结论，实验指标必须分开。
5. 对闭源模型只能观察接口暴露的轨迹摘要、token 用量、行为和延迟；没有可验证明文时，不应把模型生成的“解释”当作隐藏 CoT。
