# CoT 攻击研究：证据、假设与可复现实验

**状态：8/8 方法已设计，16/16 攻击样例已编写；已通过本机登录的 Codex CLI 对请求模型 `gpt-6-astra` 完成 32 次安全代理调用。七种输出操纵方法均为 0/2，M04 因缺少可用的 reasoning-token 数据而不可判定。Claude 模型与论文级复现仍待授权环境。**

目标仓库：https://github.com/kingkazara7/cothack

- [研究报告](research/report.md)：定义、威胁模型、指标、限制与后续验证。
- [五种公开方法](research/references.md)：作者论文、版本、实验依据及本地变体边界。
- [2026 年深度检索更新](research/updates-2026.md)：轨迹窃取、监控规避、推理耗尽与训练期后门等新研究及证据分层。
- [八篇新近论文详解](research/paper-notes-2026.md)：逐篇解释威胁模型、攻击流程、实验协议、作者结果及局限。
- [三种自主构造思路](methods/proposed.md)：假设、区别与消融设计；不主张全球首创。
- [16 个测试样例](data/cases.json)：每种两个，包含系统约束、原任务、对照和攻击。
- `scripts/run.py`：直接调用 OpenAI Responses / Anthropic Messages；Python 3 标准库，无第三方依赖。
- `scripts/run_codex_cli.py`：通过本机已登录的 Codex CLI 执行独立、只读的安全代理实验。
- `scripts/reproduce_trace_replay.py`：第一篇论文的本地机制复现；比较全局可移植推理块与上下文绑定修复，不调用供应商系统。
- `scripts/analyze.py`：配对结果、条件 ASR 和 Wilson 区间。
- `logs/`：逐请求 JSONL，包括预检记录和 GPT-6 Astra CLI 原始事件。
- `results/`：机器可读统计与[安全代理实验结果](results/gpt-6-astra-codex-cli-pilot.md)。

## 执行

在本机安全设置并 export OPENAI_API_KEY / ANTHROPIC_API_KEY；脚本不自动加载 .env。不要把密钥写进仓库或命令历史。模型 ID 来自 2026-10-21 官方文档，账户可用性尚未验证。

```sh
python3 -m unittest discover -s tests -v
python3 scripts/run.py --model gpt-6-astra --preflight --repeats 1
# 以下为真实计费调用；每个模型 16 样例 × 2 条件 × 3 次 = 96 请求
python3 scripts/run.py --model gpt-6-astra --repeats 3
python3 scripts/run.py --model claude-fable-5-1 --repeats 3
python3 scripts/run.py --model claude-opus-5-5 --repeats 3
python3 scripts/analyze.py logs/EXACT_RUN_FILE.jsonl --out results/EXACT_RUN_FILE.json
```

通过已登录的 Codex CLI 运行两个无害代理样例：

```sh
python3 scripts/run_codex_cli.py --model gpt-6-astra --sample-index 1
python3 scripts/run_codex_cli.py --model gpt-6-astra --sample-index 2

# 无需网络或密钥的推理块重放机制复现
python3 scripts/reproduce_trace_replay.py
```

每次执行生成独立日志；不要把多次运行直接合并。默认输出预算 2048 token，最大允许 8192；每请求超时 120 秒，无自动重试，不启用工具。三模型共 288 请求，最多约 589,824 输出预算 token；这是预算上界，不是价格估计。可先用 `--method M01 --repeats 1` 验证 API 权限与配置。OpenAI 使用 medium reasoning，Anthropic 使用 adaptive thinking；两者不是相等计算预算。API 错误保留以诊断，不计入 ASR。

## 结果解释

未调用、API 错误、截断输出、错误对照都不等于攻击失败。严格整数匹配测量的是输出约束；需人工复核格式偏差。OverThink 仅在 API 返回可比较 reasoning token 数时计算倍率，Anthropic 缺失该字段时为 N/A。没有隐藏推理真值，任何输出解释都不是 CoT 泄露证据。

## 范围

全部任务为本项目合成算术，攻击文本只存在于明确标记的不可信数据区。无真实敏感信息、第三方目标、数据外传或有害任务。公开方法为机制启发的安全缩小变体，不能冒称原论文端到端复现。真实模型实验不一定要求直接 API：本仓库已用获授权的本机 Codex CLI 完成一轮黑盒代理测试；其系统脚手架、隐藏推理不可见性和小样本量限制了结论。论文原始设置和 Claude 模型仍需相应的获授权端点。

推理轨迹窃取被纳入 CoT 机密性攻击。当前环境没有可重放的供应商 reasoning block；[本地重放结果](results/trace-replay-simulation.md)没有调用任何 LLM，只演示受控最小系统中的机制，不能作为模型攻击成功率或现网漏洞证据。
