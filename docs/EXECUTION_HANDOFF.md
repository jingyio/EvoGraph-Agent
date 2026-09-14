# 给执行 session 的交接

用户已将原 session 定位为讨论 session，并计划自行新建执行 session。执行 session 无需读取全部聊天记录，也不要假定自己继承了浏览器变量、shell session 或未提交文件。

2026-09-14 当前工作单元为 TODO P0.4：用户文本匹配、计算/本地产物图复用、工作区反馈
修订。详细规格与启动命令见 [当前交接](workspace-graph-evolution-handoff-2026-09-14.md)。
旧 P0.1 不再是当前优先项，下面启动提示已同步为 P0.4。

## 启动提示词（可直接粘贴）

```text
请在 /Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab 接管这个项目的执行工作。

先检查 Git 状态，然后依次阅读：
AGENTS.md
.codex/state.md
docs/ARCHITECTURE.md
docs/DESIGN_DECISIONS.md
docs/EXPERIMENT_STATUS.md
docs/TODO.md

以代码和原始运行记录核验文档。原 session 用于讨论，这个 session 负责落实已确认设计、调试、测试与 Git 提交。

先读 docs/workspace-graph-evolution-handoff-2026-09-14.md，推进 TODO P0.4：用户文本到历史图匹配、计算与已有本地产物节点复用、工作区 train 反馈修订。先完成机制与协议回归、小规模预检，再在预算条件满足时新建严格串行 48-task 对照。验收必须有真实图变化和后续使用；未发生不能虚构进化。不根据验证/测试轨迹学习，不硬编码答案，不额外跑图验证 rollout。

每个阶段报告与导师目标的关系、真实验证结果和局限。保留已有改动和全部实验失败。完成后更新 TODO、EXPERIMENT_STATUS、.codex/state.md，并创建可审查的本地 Git 提交；不要泄露或提交 .env 和原始 artifacts。
```

## 协作与状态同步

- 讨论 session：讨论架构、实验归因、取舍；已确认结论写入 DESIGN_DECISIONS，未定想法写入 TODO 并标记提案。
- 执行 session：先核对文档与 Git，再推进一个有验收标准的工作单元；常规修复和实现决策自行处理，不把跨 session 协作变成逐步审批。
- 同一工作目录只保留一个代码写入者。讨论 session 需要修改文档时先检查工作树，避免同时编辑同一文件。隔离 worktree 可选，但先核查其私有数据/配置是否齐备。
- 阶段结束记录：提交、实现变化、检查、原始证据位置、未解决问题、下一步。不要只在聊天末尾留总结。
- 无需强制选用某个模型昵称。角色由任务与文档确定，所用模型的实际配置以工具/运行记录为准。
- 文档与代码冲突时，最新用户决定定义目标，代码定义当前行为，原始证据定义实验事实；明确记下差异，不能把目标写成现状。
