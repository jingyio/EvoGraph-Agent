# 下一阶段任务

日期：2026-09-11。目标见 [mentor-goals.md](mentor-goals.md)，已确认边界见 [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)。此表是工作优先级，不是已完成能力清单。最终严格串行 36-task 对照已经完成；任何后续实验必须另建协议和实验 ID，不能回写或拼接现有结果。

## P0.3 Workpack V12 服务与恢复诊断

状态：**full train 已完成但不合格，2026-09-13**。V12 的共享重复 compute guard
通过 smoke 和 12-task precheck；48 对 full 出现 Baseline 3 次有界业务/报告失败、
一条 Baseline 模型超时，以及末尾两条两臂共同模型网络失败。详情见
[V12 结果](workspace-workpack-v12-results-2026-09-13.md)。

- 不重跑或拼接 V12 成功子集；表面 token -40.513% 不能作为同质量结论。
- 若继续 Workpack，先以独立诊断定位模型网络连接失败与 Baseline 报告恢复差异；稳定后
  建立新的 runtime/service 版本，从 smoke 开始，不覆盖任何 V11/V12 artifact。
- Composition 仍为 0；下一步不能通过调低阈值制造命中。

## P0.0 端到端在线对照

状态：**完成，2026-09-11**。`online-rsi-serial-final-v4` 使用独立空经验、固定36条 train manifest 和 `run=model=read=1`。两臂均36/36；Agent token 539,468→347,368（-35.6%），达到约30%目标；模型请求203→114；工具274→277。全部六个 family 正向，`cancelled_payments` 为 -44.0%。结果、Judge 覆盖缺口和展示入口见 [online-rsi-serial-final-results-2026-09-11.md](online-rsi-serial-final-results-2026-09-11.md)。

- AutoTool/TIG 惯性执行已退役，不再进行触发调优或新增实验；旧记录保留。
- 旧负收益、分时匹配和 RSI-only 修复工件全部保留，不改写历史；最终 V4 是唯一可作为本轮严格全量结论的工件。

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

状态：未完成；最终 V4 只证明 G0 形成与 Fast 复用，没有真实多代案例。

- 从正常 train 运行的真实问题与有效恢复建立 `父图→Patch→子图→后续使用` 链。
- 未知错误不自动修复，验证/测试运行不能提供学习样本；注入异常仅能作为标明的回归测试。
- 验收：每个节点有 run ID、图 diff、适用范围、有效修复证据与实际后续运行；没有第二代改进就如实停止，不为完成任务而捏造演化。

## P1.2 分离 Plan 复用与图执行贡献

状态：2026-09-10 已部分落实；`plan_react_reuse` 与 UI/冻结评测选项已加入，单条 train 对照已记录，完整冻结评测待执行。

- `plan_react_reuse` 复用选中版本的 Plan，不执行图、不更新进化证据；冻结评测会把同一图快照传给两臂。
- 初始 train 对照显示编译 Motif token/模型请求更低而延迟略高；保留该反例，不替代冻结评测。
- 验收：任务、模型、通用提示、预算、计费范围可比；报告全部尝试与成功子集，独立列冷启动与来源成本。

## P1.3 Judge 完整性与质量校准

状态：最终 V4 已尝试36对，完成26对、10个服务超时；同模型且15个顺序分歧，不能视作独立质量判定。

- 先检查现有四对理由与数据，包括顺序分歧；评估是否需要独立更强裁判。配置必须用用户可用的模型，不能猜型号或声称同模型独立。
- 需要全量结论时固定 rubric/模型/样本，再补完裁判；如补批处理，保持有界并发、可取消、失败费用保留与不因胜负重试。
- 当前三维0–10、权重50/30/20、双顺序平均 reward 保持为已确认协议；新权重是新实验版本，不覆盖旧分数。
- 验收：格式失败不计零；reward 不覆盖硬校验；小差异和顺序分歧不被包装为显著胜负。

## P1.4 重复任务可靠性与最终展示

状态：主展示已完成，默认入口为 `#home`，可直接进入同任务对比、RSI 指标/严格审计和逐任务 DAG 回放。若后续继续，只能预先固定新的代表任务和重复次数；不能把本轮36个 train 结果重复运行后挑选最好一次。

- 在选定验证任务上做有限重复实验，统计质量、参数错误、上限触发、恢复、均值和波动；不预设 RSI 零错误。
- 改动稳定后冻结方案，另做 test 评估，测试反馈不得回流学习。
- 最终视频应包括相同业务成果、真实成本对照、实际 G0→Fast 使用链及限制。优先使用 `#home`（一个企业运营员工：业务需求、实际 HTML 简报、当前参数绑定和工作记录回放）→ `#compare`（全量36对、三领域按真实保存事件索引推进的对比轨道）→ `#insights` → `#replay?task=finance-cancelled_payments-02`（模型调度工具与图执行器调度工具、绑定和 DAG 高亮），不制作虚构时间线；没有真实 G1/G2 时不展示图修改链。
- 若需要真正的 PPTX 产物，另立设计/验收：必须从保存的提交事实与观察证据生成、渲染核验，并明确它是展示交付物而非实验结果；当前仅有 HTML 简报，不能改名为 PPT。
- 在线录制入口 `#live` 已可运行真实 `plan_react` 与 `graph_rsi` 的 1/2 个 train 任务序列；它必须保持独立 artifact、费用确认和单会话限制。当前预算暂停：**未经新的用户预算授权，不启动额外模型运行**。可先回放已保存 session，不能把演示会话合入正式实验。
- `online-rsi-all-train-saturation-v3` 的 token/请求/工具/结果可作为冷启动诊断展示；其 `runtimeOverhead` 归因错误，禁止用于本地 overhead 或饱和结论。V4 部分运行保留但不作为比较样本。

## P1.5 AutoTool / TIG

状态：退役。历史负向机制与回放字段保留，但不再实施惯性执行、学习更新、触发调优或新对照。

## 暂不扩展

独立 Agent 平台、大而全 IR、多候选昂贵 rollout、无来源企业数据、新增真实业务写权限、未经实验支持的论文创新结论。当前也没有要求自动创建新 session、安排定时任务或切换模型。

## 执行记录约定

完成一项后在本文件标注日期/提交/证据链接；更新 EXPERIMENT_STATUS 与 `.codex/state.md`。新想法先标“提案”，不要覆盖已确认决策。下一任务不明确时，可以先完成相关只读诊断；常规实现选择不必反复询问。
