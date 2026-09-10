# 修复后在线 RSI 匹配 Baseline 结果

日期：2026-09-10。RSI 来源为 `artifacts/online-e2e/online-rsi-graph-precheck-v3/`；新 Baseline 与配对汇总为 `artifacts/online-e2e/online-rsi-graph-matched-v4/`。二者均不纳入 Git。

## 协议与复用审计

- 两侧使用同一冻结 36-task train manifest，任务哈希为 `329894...e6b3490`；六个 family 各六条不同记录，顺序相同。
- RSI 来源从独立空经验开始，36/36 完成；前六条冷启动产生六个 G0，后 30 条实际 Fast 使用对应 family 的 G0。运行记录有来源 run ID、版本 ID、经验前后快照和完整 usage；未出现维护错误或遗漏 usage。
- Baseline 在新隔离目录中串行执行，`learning_enabled=False`；执行/规划模型均为 `qwen/qwen3.5-27b`，最大 24 步、180 秒任务超时、单 Agent/模型/读取并发，通用提示、工具契约和有界报告恢复与 RSI 相同。
- 这是 `time_separated_matched` 对照：token、请求和工具调用可按匹配协议比较；延迟会受不同时段服务负载和缓存影响，不能称为严格同时段性能试验。
- 来源工件记录模型名、预算、源码 revision 和客户端设置，但为避免泄露配置没有记录 provider endpoint 的历史指纹；因此“同一模型服务端点”依赖本轮配置连续性，不能在事后独立重建。该限制不影响已记录 token，但限制可复现性表述。

运行器在复用 RSI source 前校验 manifest、RSI 为空经验/可学习协议、每一条 RSI 成功状态，以及当前记录的模型、预算、串行、任务哈希和影子 rollout 设置。RSI-only 已完成但误标 `running` 的汇总 bug 已修复；状态重放没有发出模型或工具请求。

## 全量结果

| 指标 | Plan + ReAct Baseline | Graph RSI | RSI 相对 Baseline |
|---|---:|---:|---:|
| 结构化通过 | 32 / 36 | 36 / 36 | +4 任务 |
| 输入 / 输出 / 总 token | 476,829 / 32,801 / 509,630 | 360,076 / 26,737 / 386,813 | **-122,817 / -24.1%** |
| 模型请求 | 197 | 104 | -93 |
| 工具调用 | 266 | 331 | +65 |
| Agent 累计端到端时间 | 648.18s | 502.10s | -146.08s / -22.5% |
| 每成功任务 token | 15,926 | 10,745 | -32.5% |
| 平均 / P95 / 最大单任务延迟 | 18.00 / 40.06 / 44.33s | 13.95 / 30.95 / 35.66s | 分时测量，仅作观测 |
| 最大单任务 token | 24,382 | 34,340 | RSI 最大值在 `cancelled_payments-05` |
| 工具错误 / 经验维护错误 | 0 / 0 | 0 / 0 | — |
| 报告提交 / 初次失败 | 41 / 9 | 45 / 9 | — |

全量 token 下降 **24.1%**，因此“约 30%”交付目标 **未达到**。没有可靠价格配置，未虚构美元成本。Judge 与 Agent 成本分开：36 对双顺序 Judge 为 72 次请求、336,757 token、466.39s；执行器和 Judge 同为 `qwen/qwen3.5-27b`。

Baseline 的四项失败均为 `finance-cancelled_payments-{01,03,05,06}` 的 `evidence_coverage`；每项最多两次报告提交后 `limited`，没有重读、无限重试或服务错误。RSI 没有结构化失败。Judge 仍给部分 Baseline 失败报告较高文字 reward，因为它只评价提交文本和冻结证据；该 reward 不覆盖确定性失败。

## Family 内成本与实际复用

| Family | Baseline 通过 / token | RSI 通过 / token | RSI token 差异 | 冷启动后实际 Fast 复用 | 结论 |
|---|---:|---:|---:|---:|---|
| finance/cancelled_payments | 2/6 / 80,729 | 6/6 / 143,418 | **+77.7%** | 5 | 负收益；G0 筛选后补查仍有更多详情工具和 token |
| finance/installments | 6/6 / 127,197 | 6/6 / 82,684 | -35.0% | 5 | 获益 |
| support/channels | 6/6 / 82,725 | 6/6 / 50,348 | -39.1% | 5 | 获益 |
| support/timeliness | 6/6 / 69,609 | 6/6 / 43,118 | -38.1% | 5 | 获益 |
| tickets/unassigned | 6/6 / 67,187 | 6/6 / 34,933 | -48.0% | 5 | 获益 |
| tickets/labels | 6/6 / 82,183 | 6/6 / 32,312 | -60.7% | 5 | 获益 |

五个 family 从第一个任务即保持累计 token 正节省；`cancelled_payments` 六个点均未回本。六条记录不相同，曲线本身不是进化因果证明；可信证据是每个热启动任务引用了首任务产生的特定 Workflow ID，且 Fast 路径跳过完整 Plan。没有 Composition 命中；没有因正常反馈产生的 G1/G2 结构修订。六个 G0 的首次保存、支持度增长和程序修复均不称为自主结构进化。

## 质量与可靠性

- 确定性结构化质量：RSI 36/36，Baseline 32/36。RSI 未发生工具或维护错误；Baseline 四个有界报告失败保留在分母。
- Judge 平均 reward：Baseline `0.9768`，RSI `0.9746`；18 对顺序一致、18 对顺序分歧，胜负统计为 Baseline 3、RSI 2、平局 13、inconclusive 18。该文字差异不支持质量优劣结论，更不能抵消确定性失败。
- 延迟：RSI 累计较低，但它是分时运行，不能将 -22.5% 解释为稳定实时性能优势。应以 token、请求、工具和确定性结果作为本轮主要效率/可靠性证据。

## 展示与结论边界

可录制入口：`/api/online-e2e/online-rsi-graph-matched-v4/report`。页面按 family 显示六个到达实例的经验前后、Workflow 形成/使用、路径、成本、累计节省和准确的 trace/report 链接；只显示真实事件。

本轮证明了在线经验积累和跨任务复用改变了后续执行，并在五个 family 的完整六任务成本上带来降低；但没有证明多代结构进化、Composition 收益、独立 Judge 质量优势或 30% 全量 token 目标。旧 `online-e2e-train-v1` 仍是负收益历史证据，未被改写。
