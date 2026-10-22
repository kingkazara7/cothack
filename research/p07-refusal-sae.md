# 补充方向：Understanding Refusal with Sparse Autoencoders

整理日期：2026-10-22（America/New_York）。本条目是正式 P01–P05 之外的 SAE 安全研究背景，不计入“5 篇公开方法 + 3 种自拟方法”的八方法统计，也不作为 N03 的实验结果。

## 论文与代码

Wei Jie Yeo、Nirmalendu Prakash、Clement Neo、Ranjan Satapathy、Roy Ka-Wei Lee、Erik Cambria，*Understanding Refusal in Language Models with Sparse Autoencoders*，Findings of EMNLP 2025，页 6377–6399。

- 论文：[ACL Anthology](https://aclanthology.org/2025.findings-emnlp.338/)；[PDF](https://aclanthology.org/2025.findings-emnlp.338.pdf)；DOI [`10.18653/v1/2025.findings-emnlp.338`](https://doi.org/10.18653/v1/2025.findings-emnlp.338)
- 作者代码：[SenticNet/Refusal-SAE](https://github.com/SenticNet/Refusal-SAE)；上游仓库：[wj210/refusal_sae](https://github.com/wj210/refusal_sae)

## 技术原理

论文研究的对象是安全微调模型的**拒答行为**。作者的起点是：一个“有害输入与无害输入的平均 residual activation 之差”可以形成拒答方向，但单一方向只能说明模型当前更像拒答还是服从，难以分辨哪些稀疏概念先检测到危害、哪些特征随后真正触发拒答。SAE 将某层 residual activation 编码成过完备而稀疏的 feature activations，再通过 decoder directions 重构回 residual stream，使研究者可以逐 feature 做归因和干预。

作者提出 `CosSim+AP` 两阶段特征搜索：

1. **计算拒答方向。** 在每层缓存有害与无害指令的 residual activations，取两组均值之差作为该层拒答方向，并遍历各层选出能最好控制拒答的方向。论文对 Gemma 与 Llama 分别选中第 15 层和第 11 层方向。
2. **用方向限制候选集。** 对每一层，把 SAE decoder direction 与拒答方向计算余弦相似度，只保留最接近的 `K0=10` 个 feature。这个步骤先排除大量与拒答无关但可能被单 token loss 偶然排高的 feature。
3. **在候选 feature 上做 attribution patching。** 普通 attribution patching 需要长度相近的 clean/corrupt 输入，并主要解释一个输出 token。作者以 harmful prompt 的拒答为 clean 状态，再把投影掉拒答方向后的 activation steering 结果当作 non-refusal 的 corrupt 代理；以拒答首 token 与 steered 输出首 token 的概率差近似多 feature 的间接效应。归因分数在输入 token 上平均，然后选出 `K*=20` 个 feature，可为每个样例生成 local set，也可跨数据集平均生成 global set。
4. **做因果干预。** 作者把选中 feature 的 activation 乘常数 `c`，经 SAE decoder 投影回 reconstructed residual stream，再继续生成。负值翻转或抑制这些 feature，用来测试能否撤销拒答并诱发 jailbreak；正值用于观察正常指令是否出现过度拒答。调参后 Gemma 使用 `c=-3`，Llama 使用 `c=-1`。
5. **分开 harm 与 refusal。** 作者在 CATQA 的七类高拒答危害上分别找 global feature set。跨所有类别重复出现的共同 feature 被记为 `F_R`，解释为更靠近下游的拒答 feature；只在部分危害类别出现的 feature 被记为 `F_H`，解释为识别暴力、药物等概念的上游 harm feature。随后通过压制 `F_H` 并测量 `F_R` 的 activation 下降，检验 `harm → refusal` 的因果链。

这不是“看到某个 feature 标签像拒答，就直接宣称发现安全开关”。候选必须先与拒答方向对齐，再经过 attribution patching 排序，并以生成行为变化、随机 feature 对照、通用能力和连贯性指标验证。论文也承认，特征搜索依赖初始拒答方向，较小的 `K*` 可能漏掉其他因果 feature，而且 base-model SAE 向 chat model 的迁移并非对每个 feature 都可靠。

## 攻击目标

从攻击视角看，目标是模型的**拒答安全机制**：拥有白盒 activation 写权限的攻击者可以压低少量拒答相关 feature，使原本拒绝的模型转向服从；反方向放大 feature 也可以让无害请求出现过度拒绝，形成可用性干扰。论文还用这些 feature 解释两类黑盒 jailbreak：对有害意图做看似无害的改写，以及附加对拒答 feature 有压制作用的 suffix。

它不以读取、重写或劫持 CoT 为目标。论文只用 GSM8K、ARC 等任务检查 feature intervention 是否连带损害普通推理能力。因此，按狭义定义它不属于 Hack CoT；在本项目中，它是“SAE 可因果操纵安全行为”的相邻证据，用于说明 latent intervention 不只会改变可见文本，还可能触及安全决策链。

## 公开实验依据

- **模型与 SAE：** 论文测试安全对齐的 Gemma-2-2B 与 Llama-3.1-8B chat model，分别使用公开 GemmaScope 与 LlamaScope SAE；扩展因子分别为 32 与 8。SAE 原本在 base-model activations 上训练，论文另做迁移检查。
- **拒答干预评测：** 作者分别从 JailbreakBench、HarmBench、AdvBench 取 100 条样例，以 HarmBench classifier 判断生成是否构成实质性有害回答。作者把 activation steering 视为强上界，并比较 CosSim、activation difference、单独 attribution patching 与 `CosSim+AP`。论文图 2/9 报告 `CosSim+AP` 在两模型上都能找到可撤销拒答的紧凑 feature set；单独 CosSim 在 Gemma 上失效，单独 attribution patching 也明显较弱。
- **上游到下游的因果证据：** 压制 `F_H` 后，`F_R` 的平均 suppression rate 在 Gemma 为 `0.48`、Llama 为 `0.51`；大 100 倍的随机 feature 集合分别只有 `0.05`、`0.19`。相应拒答首 token `I` 的概率下降为 `0.71` 与 `0.37`，随机对照为 `0.06` 与 `0.04`。
- **jailbreak 机制观察：** WildJailbreak 中成功 jailbreak 相比失败样例更强地压低 `F_R`；作者也逐 token 追踪 adversarial suffix，观察到个别 framing token 会突然压低拒答 feature，并削弱上游 harm feature 对它们的剩余影响。论文明确报告，自己运行 GCG 对这两个模型无效，因此 suffix 分析改用公开 AdvSuffixes，而没有把失败隐藏掉。
- **OOD 检测：** 仅用拒答 sparse features 训练的线性 probe，在 WildJailbreak 的 vanilla/adversarial 测试上，Gemma 平均准确率为 `0.86`，对比 dense probe 的 `0.68`；Llama 为 `0.75`，对比 dense probe 的 `0.51`。这说明同一 feature set 也能作为防御检测信号。
- **能力副作用：** 论文用 1,000 条 Alpaca/Pile 测交叉熵，并在 GSM8K 与 ARC-Challenge 测准确率。`CosSim+AP` 相对基线在 Gemma 上的变化为 GSM8K `-2.1`、ARC `-0.8` 个百分点，在 Llama 上为 `+0.5`、`-4.1` 个百分点。它支持“干预较集中”，但 Llama ARC 的下降也表明不能把 feature 当成完全隔离的安全旋钮。

公开仓库给出 `benchmark.ipynb`、`cat_harm.ipynb`、`wildjailbreak.ipynb` 及对应 Python 模块。README 说明完整设置同时加载被测模型、HarmBench classifier 并计算 attribution gradients，作者使用两张 80GB GPU；单卡流程可以先运行 `src.get_features` 缓存 feature，再分阶段评测。公开代码提高了可复现性，但本项目尚未下载论文所用 checkpoint、数据集并执行这一整套流程。

## 与本项目 N03 的区别

| 维度 | Refusal-SAE 论文 | 本项目 N03 SAE Latent Counterfactual Injection |
|---|---|---|
| 目标行为 | 安全拒答/服从 | 正常选择题的目标错误答案或 thinking 生成破坏 |
| feature 选择 | 拒答方向预筛，再用 attribution patching 找因果 feature | 按 decoder 对 `logit(" A")-logit(" D")` 的投影直接选择目标 feature |
| 干预 | 将样例相关的 feature activation 乘正/负常数 | 对一个 latent coordinate 加固定 `δ`，并设 norm-matched control 与负方向 |
| 模型与 SAE | Gemma-2-2B、Llama-3.1-8B；GemmaScope/LlamaScope | Qwen3-8B；本项目紧凑 SAE fallback |
| 判据 | HarmBench jailbreak、拒答率、activation suppression、能力保持 | 指定错误选项是否出现、thinking 是否发生 feature-specific collapse |
| 与 CoT 的关系 | 只把推理任务作为副作用检查 | 直接观察正常推理生成与最终答案受 latent 注入的影响 |

因此这篇论文不会与 N03 重复：它提供“SAE feature 可以定位并移除安全拒答”的公开因果证据；N03 测的是“答案偏好相关 latent 能否在正常推理任务上定向改错或破坏 thinking”。前者的攻击面是安全 alignment，后者的攻击面是推理完整性。

## 本项目状态

当前状态为 `literature_only`：已核对正式论文、作者代码、模型、干预流程与公开结果，未在本项目服务器上运行 Refusal-SAE。它不占正式八方法中的一个位置，也没有本项目成功率。若后续复现，最低要求是固定论文代码提交与 SAE checkpoint，使用公开有害行为 benchmark，保留 HarmBench classifier 输出、随机 feature 对照、正负干预和 GSM8K/ARC 能力对照；仅观察到模型“不再说拒绝短语”不能判为成功 jailbreak。
