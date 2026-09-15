# 效率、规模与可靠性结果

日期：2026-09-10。原始工件位于忽略的 `artifacts/online-e2e/online-rsi-cancelled-optimized-v4/` 与 `artifacts/efficiency/efficiency-scale-reliability-v1/`；两者不入 Git。

## cancelled_payments 修复

旧 36-task RSI 的首个 G0 错把“支付记录”编译为订单状态详情，并对全部十条订单读取商品明细；执行模型随后再读取真正的支付记录。该错误使六条 family 累计为 143,418 token、88 次工具调用，较兼容的历史 Baseline 80,729 token 高 77.7%。

修复后编译器：

- 用意图/输出语义契约拒绝 `get_order` 充当支付记录能力；
- 以任务文本裁剪无关独立读取；
- 合并相同工具、绑定、筛选条件的等价读取节点；
- 记录本地 retrieval/selection/compile、运行时 binding、筛选掉的详情读取和空详情分支。

父图没有原地重写。早期预检 `online-rsi-cancelled-opt-v1/v2` 均保留为诊断工件；最终 `v4` 是新的、空经验的六条正式 RSI-only 流。它创建一个新的两节点 G0，后五条 Fast 复用；这是通用编译器正确性修复和经验复用，不是正常反馈产生的 G1/G2。

| 指标 | 旧 RSI 六条 | 优化 RSI 六条 | 兼容历史 Baseline 六条 |
|---|---:|---:|---:|
| 结构化通过 | 6 / 6 | 6 / 6 | 2 / 6 |
| token | 143,418 | 51,647 | 80,729 |
| 模型请求 | 26 | 15 | 31 |
| 工具调用 | 88 | 19 | 31 |
| RSI 相对 Baseline token | +77.7% | **-36.0%** | — |

每个非空任务仅执行列表加一条支付详情；空任务只执行列表。六条合计排除了 55 个不进入详情的订单绑定，空分支一次。首个冷启动的本地 retrieval/selection/compile 为 0.639/2.498/3.779 ms，两个参数绑定共 0.033 ms；这些本地数值不被换算为节省的模型调用。

该旧 Baseline 可作为**分时历史参照**：改动只在 Graph RSI 编译器、任务/模型/提示/工具/预算均匹配，但未重跑 Baseline，也不能表述为同时段严格对照。若用新 family 替换旧 36-task RSI family、其余五个 family 保留旧记录，拼接的范围指标为 295,042 / 509,630 token（-42.1%）；它不是新的严格全量实验，不能替代重新运行完整 36-task 对照。

## 记录规模

`efficiency-scale-reliability-v1` 从冻结的公开 Olist **train** 池按 10、30、60 构造互不重叠记录范围；每个范围独立用 `task_definitions.answer` 从冻结记录计算评分目标，gold 不提供给模型。10 条 RSI 冷启动，30/60 条 Fast 复用参数化图；不保存记录 ID、数量或上次规模输出。

| 记录数 | Baseline | RSI | 结果边界 |
|---:|---|---|---|
| 10 | failed，16,281 token，6 LLM，6 tools | pass，17,741 token，5 LLM，6 tools | Baseline `evidence_coverage` 两次有界失败，不能称 RSI 成本更低 |
| 30 | pass，30,329 token，7 LLM，6 tools | pass，28,531 token，4 LLM，7 tools | RSI -5.9%，筛掉 28 条详情绑定 |
| 60 | failed，56,447 token，8 LLM，9 tools | pass，41,170 token，4 LLM，9 tools | Baseline `evidence_coverage`，不能以失败臂宣称严格质量相等；RSI 筛掉 57 条详情绑定 |

两侧读取峰值均为 1。工具数随入选支付订单数和报告恢复变化，不表现为单调的每记录常数；样本三点不能主张渐近复杂度优势。

## 冻结并发与可靠性

固定四个真实 scope（10/30/60 条规模任务和一个空筛选任务），Graph RSI 经验冻结、学习关闭；任务与模型并发均设置为 1、2、4，读取并发固定为 1。运行总时间/实际 scheduler 峰值：

| 并发档 | 总时间 | 实际峰值 run/model/read | 通过 |
|---:|---:|---|---:|
| 1 | 233.71s | 1 / 1 / 1 | 3 / 4 |
| 2 | 104.64s | 2 / 2 / 1 | 4 / 4 |
| 4 | 77.57s | 4 / 4 / 1 | 4 / 4 |

并发 1 的 60 条任务报告失败为 `invalid_selection`、`selectedIds`、`evidence_coverage`，两次有界提交后停止；并发 2/4 在这一小样本均通过。它说明本次并发样本存在队列/时段敏感性，不能用后两档的成功推断 RSI 普遍更可靠，也不能称为工具并发收益：SQLite 读取的实际峰值始终为 1。

## 展示

可直接录制页面：`/api/efficiency/efficiency-scale-reliability-v1/report`。页面由保存的 JSON 生成，展示优化前后、规模结果、真实 scheduler 峰值和失败；没有虚构结构代际、并发工具加速或质量结论。
