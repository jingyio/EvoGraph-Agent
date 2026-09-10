# 下一阶段任务

日期：2026-09-10。目标见 [mentor-goals.md](mentor-goals.md)，已确认边界见 [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)。此表是工作优先级，不是已完成能力清单。当前在途工作为隔离的 36-task 在线训练对照；协议已冻结在 `online-e2e-train-protocol-2026-09-10.md`，结果产生前不得调整任务、阈值或提示以影响结果。

## P0.0 端到端在线对照

状态：2026-09-10 已保留旧负向 `online-e2e-train-v1`，并完成修复后分时匹配对照：`online-rsi-graph-precheck-v3` RSI 36/36、386,813 token；`online-rsi-graph-matched-v4` Baseline 32/36、509,630 token。匹配记录下 RSI token -24.1%，未达到 30% 目标；`cancelled_payments` 为负收益，不能用五个获益 family 掩盖。详情见 `online-rsi-matched-results-2026-09-10.md`。

- AutoTool/TIG 惯性执行已退役，不再进行触发调优或新增实验；旧记录保留。
- 下一步应只基于已保留的 `cancelled_payments` 负收益和 Baseline evidence 覆盖失败提出正常 train 流量假设；不得重跑同一批任务直到结果好看。

## P0.1 G-Agent Persistent TinyEdge 的真实训练覆盖

状态：2026-09-10 已实现 Fast / Composition / Fallback 与持久片段规范；真实 train 初试未形成可组合 support，见 [g-agent-local-composition-validation-2026-09-10.md](g-agent-local-composition-validation-2026-09-10.md)。

- Fast 命中已跳过完整 Plan；Composition 的粗子目标、确定性候选选择、直接组合执行、参数槽校验和来源 UI 均由回归覆盖。
- 下一步先解决正常 train 图编译中的上游列表歧义并积累两个以上通过的不同来源；只在真实片段 materialize 后观察 Composition，不为命中制造图或额外 rollout。
- 验收：保留所有 train 失败、模型超时和 fallback 成本；有真实命中才报告 selected IDs、当前参数绑定、工具/LLM/token/延迟和质量。未配置独立 composition 模型时不声称大小模型协同收益。

## P0.2 按需读取的训练诊断与局部图优化

状态：2026-09-10 已完成首个受限 Motif；冻结推广评估仍待执行。证据见 [motif-filter-then-enrich-validation-2026-09-10.md](motif-filter-then-enrich-validation-2026-09-10.md)。

- 问题：图可能对全量记录调用详情，Strong/Plan ReAct 能先按列表字段筛选。导师目标是减少真实 token/latency，而不是强行增加图版本。
- 已实现 `selection.kind=match` → `foreach.filter`：`finance-cancelled_payments` 的正常训练 Plan 用当前列表 `status == canceled` 筛选，支付详情只读取入选 ID；当前字段/类型变化失败关闭，无法可靠确定使用 `selection.kind=model` 交回模型。
- 两条 train 轨迹通过并保存 Motif G0；未从 validation/test 提取经验，维护额外模型/工具/影子 rollout 均为 0。结构未变化未虚增 G1。
- 后续只在冻结方案后补验证集与最终测试集评估；不得依据这些结果再修改 Motif。

## P1.1 取得真实反思进化证据

状态：待执行；机制已有受限实现，真实多代案例缺失。

- 从正常 train 运行的真实问题与有效恢复建立 `父图→Patch→子图→后续使用` 链。
- 未知错误不自动修复，验证/测试运行不能提供学习样本；注入异常仅能作为标明的回归测试。
- 验收：每个节点有 run ID、图 diff、适用范围、有效修复证据与实际后续运行；没有第二代改进就如实停止，不为完成任务而捏造演化。

## P1.2 分离 Plan 复用与图执行贡献

状态：2026-09-10 已部分落实；`plan_react_reuse` 与 UI/冻结评测选项已加入，单条 train 对照已记录，完整冻结评测待执行。

- `plan_react_reuse` 复用选中版本的 Plan，不执行图、不更新进化证据；冻结评测会把同一图快照传给两臂。
- 初始 train 对照显示编译 Motif token/模型请求更低而延迟略高；保留该反例，不替代冻结评测。
- 验收：任务、模型、通用提示、预算、计费范围可比；报告全部尝试与成功子集，独立列冷启动与来源成本。

## P1.3 Judge 完整性与质量校准

状态：每对裁判已实现，当前新版只验证四对。

- 先检查现有四对理由与数据，包括顺序分歧；评估是否需要独立更强裁判。配置必须用用户可用的模型，不能猜型号或声称同模型独立。
- 需要全量结论时固定 rubric/模型/样本，再补完裁判；如补批处理，保持有界并发、可取消、失败费用保留与不因胜负重试。
- 当前三维0–10、权重50/30/20、双顺序平均 reward 保持为已确认协议；新权重是新实验版本，不覆盖旧分数。
- 验收：格式失败不计零；reward 不覆盖硬校验；小差异和顺序分歧不被包装为显著胜负。

## P1.4 重复任务可靠性与最终展示

状态：待执行，依赖明确的图版本与质量判定。

- 在选定验证任务上做有限重复实验，统计质量、参数错误、上限触发、恢复、均值和波动；不预设 RSI 零错误。
- 改动稳定后冻结方案，另做 test 评估，测试反馈不得回流学习。
- 最终视频应包括相同业务成果、真实成本对照、真实图修改及后续受益。使用 `#demo` 回放与业务报告，不制作虚构时间线。

## P1.5 AutoTool / TIG

状态：退役。历史负向机制与回放字段保留，但不再实施惯性执行、学习更新、触发调优或新对照。

## 暂不扩展

独立 Agent 平台、大而全 IR、多候选昂贵 rollout、无来源企业数据、新增真实业务写权限、未经实验支持的论文创新结论。当前也没有要求自动创建新 session、安排定时任务或切换模型。

## 执行记录约定

完成一项后在本文件标注日期/提交/证据链接；更新 EXPERIMENT_STATUS 与 `.codex/state.md`。新想法先标“提案”，不要覆盖已确认决策。下一任务不明确时，可以先完成相关只读诊断；常规实现选择不必反复询问。
