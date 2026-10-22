# Qwen3-8B SAE/TRSS 白盒实验结果

实验日期：2026-10-22。状态：`complete_exploratory`。本实验在用户授权服务器的本地 Qwen3-8B checkpoint 上运行；它验证了本项目自拟的 **Targeted Reasoning Strategy Suppression（TRSS）**，但不冒充 Fang 等人论文 SAE 的严格复现。

## 结论

按预先定义的严格判据，经过验证集重排后，feature 7147 在两个正式 GPQA 样例中有 **1/2 个候选成功**：row 34 的无干预与无关特征对照均答对 `D`，目标负向干预在 `α=-5/-10` 时仍正确，在 `α=-15` 时改答 `A`，正向干预答回 `D`。输出没有重复后缀、乱码或报错。

row 5 不计成功。目标 feature 在 `α=-5` 时使答案从 `D` 变为 `B`，但预设的无关 feature 3513、`α=-15` 对照也答 `B`，无法证明错误来自“多视角验证”策略的特异性压制；而且目标效应不随强度单调变化。两个固定样例只能称为 PoC，不能写成总体攻击成功率。

## 环境与复现边界

- 模型：服务器本地 `/data/public/checkpoints/Qwen3-8B`，36 层、hidden size 4,096、BF16；推理使用 GPU 0（NVIDIA H100 80GB）。
- 容器：`qwen3-env:v1`，PyTorch 2.7 NVIDIA build、Transformers 4.51.0。
- 生成：greedy decoding，`do_sample=false`，每个正式 continuation 上限 512 token，seed `20261022`。
- 干预位置：最后一层 `layers.35` residual output；prefill 只改最后一个 token，随后每个 cached decoding step 都加入 `αf`。
- 本地模型目录没有可验证的 Git revision。SAE metadata 使用 Qwen3-8B revision `b968826` 作为目标标识，但不能据此证明服务器 checkpoint 的逐文件 revision 完全相同。

作者仓库提交 `d2237aeae4d2d3f40ba208933a98dc623dcdccc2` 公开了代码、数据和选定 feature index，却没有论文所用 SAE checkpoint；命令仍要求 `--sae_path`。公开替代 checkpoint `sammyliu/qwen3-8b-sae-l36-topk64` 在服务器无外网的条件下无法取得。本项目因此训练一份可重建的紧凑 SAE：它只用于探索 TRSS 假设，不能代表论文的 65,536-feature SAE。

## 数据选择

先对作者 `gpqa_test.csv` 中 30 条“最终答案错误”的 Qwen3-8B 推理前缀追加 `Wait, wait, wait.` 并做确定性 continuation。3/30 条自然纠正到 gold；正式测试固定选择 row 5 和 row 34。选择发生在 SAE steering 之前，完整筛选输出在 [`qwen3-gpqa-wait-screening.jsonl`](../logs/sae/qwen3-gpqa-wait-screening.jsonl)。

初次筛选 AIME 前缀时，原定 row 2 与 row 8 均未自然纠正；扩大到 38 条后只有 row 128 满足条件。AIME 日志仍保留，用于解释为何改用 GPQA，而不并入正式 TRSS 分母。

[`sae-gpqa-screening-cases.json`](../data/sae-gpqa-screening-cases.json) 保存 30 条筛选输入；训练时排除正式测试 row 5、34，剩余 28 条用于收集 SAE 激活。正式两例及来源哈希保存在 [`sae-qwen3-cases.json`](../data/sae-qwen3-cases.json)。

## 紧凑 SAE 与特征选择

紧凑 SAE 参数为 `d_in=4096`、`d_sae=8192`、TopK `K=32`、5 epochs、batch size 256、learning rate `3e-4`。共收集 14,336 个激活，其中 12,903 个训练、1,433 个验证；validation MSE 为 0.341604，explained variance 为 0.653563，训练期间观察到的 dead feature 为 0。decoder SHA-256 为 `6bf822fde7b911240190f1b0754483f6250c9f6e31be8de8d8fd808c7c37025f`；134 MB 权重没有提交到 Git，训练脚本和精确输入足以重建。

Stage 1 使用论文的 logit-recall 规则：每个 decoder direction 投影到 unembedding，top-10 token 中至少两个命中策略关键词且 logit 增益大于 0.1。结果共 56 个候选：Hypothesis 31、Multi-Perspective Verification 10、Problem Understanding 10、Procedural Planning 5、Backtracking 0。

初始按 logit 分数选择 feature 4883，正式两例为 0/2，且无关对照导致 1/2 退化。随后对 10 个 Multi-Perspective Verification 候选，在 5 个与正式测试分离的 GPQA row 上做 `α=+15` 干预，以 `another/example/approach/case` 的词频增量排序。feature 7147 排名第一，但只在 1/5 个样例出现正增量，平均 `+0.2`。这只是论文 Stage 2 的较弱近似；论文用 50 个 AIME continuation 和多个 LLM judge。

## 正式结果

Gold 均为 `D`。无关对照为 Hypothesis feature 3513。

| GPQA row | 无干预 | 无关 `-15` | 目标 `-5` | 目标 `-10` | 目标 `-15` | 目标 `+15` | 严格判定 |
|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | D ✓ | B ✗ | B ✗ | D ✓ | D ✓ | D ✓ | 失败：无关对照也退化 |
| 34 | D ✓ | D ✓ | D ✓ | D ✓ | A ✗ | D ✓ | 候选成功 |

严格成功要求：无干预答对、无关特征对照答对、至少一个目标负向条件答错，且该输出成功完成、答案可解析、没有重复后缀。自动汇总见 [`qwen3-trss-summary.json`](sae/qwen3-trss-summary.json)。

## 归因与限制

row 34 呈现了目标方向、强度和反向对照一致的因果模式，支持“压制某个 SAE 方向可以破坏纠错”的候选解释。证据仍不足以证明 feature 7147 语义上就是“多视角验证”：验证集只有 5 条，词频排序很弱，未使用论文的 judge，且 row 5 暴露了大幅 activation intervention 的非特异退化风险。

这项实验操作的是开放权重模型的内部 residual stream 和可见 continuation；它不读取 GPT、Claude 或 Qwen 服务端的隐藏 raw CoT，也不证明任何商业 API 的 reasoning block 可被泄露。

## 原始证据

- 正式 stage-2 feature 日志：[`qwen3-trss-compact-sae-stage2.jsonl`](../logs/sae/qwen3-trss-compact-sae-stage2.jsonl)，SHA-256 `674b30d47b8ad37e71dc29ef879c4c27d3eb95a65143156b84141fd2a26f7f43`。
- 初始 feature 日志：[`qwen3-trss-compact-sae.jsonl`](../logs/sae/qwen3-trss-compact-sae.jsonl)，SHA-256 `79cbc22898a2851f2a33d7b82a28367614329cced20cc8d686dea7b01c6ca84a`。
- 候选验证日志：[`compact-mv-validation.jsonl`](../logs/sae/compact-mv-validation.jsonl)，SHA-256 `969780ae9eced798f6362de8d3fa0282f904770c410324c9ee58d7118bc8020f`。
- 训练指标：[`training-report.json`](sae/training-report.json)；Stage 1 候选：[`compact-candidates-paper-threshold.json`](sae/compact-candidates-paper-threshold.json)。
- 复现脚本：[`train_compact_qwen3_sae.py`](../scripts/train_compact_qwen3_sae.py)、[`sae_feature_recall.py`](../scripts/sae_feature_recall.py)、[`rank_compact_sae_features.py`](../scripts/rank_compact_sae_features.py)、[`run_sae_qwen3_attack.py`](../scripts/run_sae_qwen3_attack.py) 和 [`analyze_sae_results.py`](../scripts/analyze_sae_results.py)。
