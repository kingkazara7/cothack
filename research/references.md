# 公开方法与证据

检索日期：2026-10-21（America/New_York）。以下均为作者论文；数字是作者报告，不是本仓库实测。版本号用于避免不同版本混用。

## M01 H-CoT

- 原文：https://arxiv.org/html/2502.12893v2
- 原理：复用或模仿执行阶段的推理，诱导跳过安全判断。
- 公开实验依据：o1/o3、DeepSeek-R1、Gemini 等；原文 §4–5，Malicious-Educator 基准。
- 本地变体边界：这里只用合成策略约束模拟跳过判断，没有复用真实隐藏推理。

## M02 Chain-of-Thought Hijacking

- 原文：https://arxiv.org/html/2510.26418v4
- 原理：以无害谜题占用长推理，再切换到攻击目标。
- 公开实验依据：原文摘要报告在 HarmBench 四个旧模型上 ASR 为 99%、94%、100%、94%；§3、附录 E。
- 本地变体边界：本实验仅短预算变体，不能声称复现论文长推理或其 ASR。

## M03 CoT Forgery / Role Confusion

- 原文：https://arxiv.org/html/2603.12277
- 原理：把不可信文本写成已完成的自我推理，试图继承内部角色权限。
- 公开实验依据：原文 §3 区分聊天越狱和代理劫持，并进行风格消融及角色探针分析。
- 本地变体边界：只模拟文本角色伪造，不访问内部激活，也不证明潜在角色混淆。

## M04 OverThink

- 原文：https://arxiv.org/html/2502.02542v5
- 原理：在外部内容中放入与任务无关的推理诱饵，增加计算开销。
- 公开实验依据：原文 §4–5；v5 在 FreshQA、SQuAD、MuSR 分别报告最高 13×、46×、12× 推理开销。
- 本地变体边界：短诱饵、固定预算；以 API reasoning token 为指标，延迟仅辅助。

## M05 CatAttack

- 原文：https://arxiv.org/html/2503.01781v2
- 原理：给数学问题附加无关短触发句，观察语义不变时错误率是否增加。
- 公开实验依据：原文 §2–3 使用代理模型搜索触发并迁移到推理模型；报告相对错误率上升。
- 本地变体边界：使用公开示例触发句，不重新执行代理模型优化；两道题不能代表原始基准。

## 接口文档

- https://developers.openai.com/api/docs/models/gpt-6-astra
- https://developers.openai.com/api/docs/guides/reasoning
- https://platform.claude.com/docs/en/api/messages/create
- https://platform.claude.com/docs/en/models/fable-5-1/overview
- https://platform.claude.com/docs/en/models/overview

公开模型名不代表当前账户有调用权限。论文结论也不能外推到题目指定的新模型。
