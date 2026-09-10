# 用正常任务验证的 Graph RSI

新增任务策略 `graph_rsi` 和 `/api/taskbank/evolution`。前端 `#evolution` 默认展示公开真实历史数据任务库上的在线版本链；旧合成沙箱代码、专用记录与 API 已按用户要求移除；有日期的实验文档只作为历史证据。

```text
首次正常训练任务：Plan → 自动读取图（包含已知字段复用优化） → 模型报告 → 结构化评分
成功轨迹：保存 G0 → 本地字段覆盖分析 → 如有修改，保存带恢复分支的 G1
后续同类任务：匹配已有版本 → 直接执行读取图 → 模型报告 → 更新版本证据
图失败：保留成功观察 → 本次任务交给模型 → 有效修复生成子版本 / 无依据则待分析
```

候选只在下一次正常提交的任务中执行。版本维护模块不持有模型客户端或工具执行接口，不生成影子 rollout。冷启动执行正常 Plan，保留现有字段消除并直接使用带恢复的版本 C，不故意执行冗余节点制造版本演化。已有保守图的正常成功轨迹仍可触发复用 Patch。冷启动开销保留在累计成本中，不能只展示热启动成本。已有的 `autotool` 策略仍每次生成计划和自动图，供对照。

## 计量

- `metrics` 记录正常任务的全部模型请求、输入/输出 token、工具调用（含恢复失败）、错误、队列等待及执行延迟。
- `evolution.lookupMs` 记录版本匹配和验证耗时，已在任务执行延迟内。
- `evolution.maintenanceMs` 记录本地反思、Patch、证据更新和持久化耗时，并加进任务总延迟。
- `extraModelRequests / extraToolCalls / shadowRollouts` 指版本维护额外发起的工作，当前三项均为 0。它不表示正常任务恢复免费，也不表示总体 overhead 为零。
- 没有配置模型价格时不估算美元成本；用实际输入/输出 token 展示。报告文字质量未评分。

图内消除计数表示实际避免了逐 ID 详情调用，和 ReAct 的净差异需通过同任务工具轨迹另算。自然任务成本可以展示趋势，不能作同任务反事实；最终效率结论仍需冻结图版本、同模型与同评分器的成对实验，并把冷启动和维护成本摊入总量。

## 使用

```text
POST /api/taskbank/runs
{"taskId":"tickets-unassigned-02","strategy":"graph_rsi"}

GET /api/taskbank/evolution
GET /api/taskbank/runs/<run-id>
```

一条 POST 仅运行该任务一次。前端可连续选择同类 train/validation 任务，看到来源轨迹、父子图 ID、Patch、图使用证据、token、延迟和维护开销。持久化位于 `artifacts/online-graphs.json`；任务原始轨迹仍位于 `artifacts/taskbank-runs/`，两者不提交 Git。

工具图协议与数据划分见 [graph-ir.md](graph-ir.md)。已有回归测试覆盖字段缺失逐条补查、图失败后模型恢复生成子版本、重复结构不增版、版本重启恢复、语境/契约隔离和测试集不回写；注入测试不作为真实模型进化成果。
