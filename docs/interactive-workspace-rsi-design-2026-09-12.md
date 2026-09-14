# 交互式工作区与新工作包最小设计

日期：2026-09-12。本文定义新增工作台和工作包协议；不改写
`online-rsi-serial-final-v4`，也不把其公开历史数据结果与本协议的新实验合并。

## 1. 目标与非目标

工作台接收自然语言工作请求和 CSV、XLSX、TXT、JSON 资料，按当前资料的
表、字段和行运行同一套 `TaskRunner`。它不是固定 `taskId` 的聊天皮肤，也
不是可执行上传内容、任意代码或企业写入平台。

- 三个角色：财务运营、客服运营、技术工单运营。
- 所有业务工具只读；草稿、报告和导出只写入当前工作区的本地 artifacts。
- 用户资料不进入共享 RSI 经验、展示 DTO、Git 或任何评测训练集。
- AutoTool/TIG 惯性执行继续关闭。现有 BM25、契约和图执行器不因本设计删除。
- 不新增大型 IR：工作区任务仍是现有 Python `dict`、JSON Schema `Tool` 和
  `TaskRunner` 运行时。

## 2. 模块边界

`WorkspaceManager` 负责每个工作区的目录、解析结果、文件清单、报告索引和
不可变任务快照。`WorkspaceBank` 提供与 `TaskBank` 相同的
`task(taskId)`、`tools(taskId)`、`root` 接口，因此 Baseline 与 RSI 共用
`TaskRunner`、报告恢复、工具 trace 和回放格式。

`WorkspaceRunner` 只读取当前工作区任务。普通用户请求使用独立运行目录和
`learning_enabled=False`；它不会读取或更新正式实验经验。预定义工作包在独立
实验目录创建 `TaskRunner`：Baseline 不学习，RSI 从空 store 开始，只有
`split=train` 且确定性规则通过才调用既有 `OnlineEvolution.observe`。

图复用的匹配键包含场景、工作流类型、规范化任务模板、当前表/列契约和工具契约。
历史图只携带操作结构和参数槽；绑定只来自当前文件的 table、column、row ID。
契约或 schema 不一致时拒绝 Fast，回到完整 Plan，不能按文字相似度套用旧图。

工作区的完整 Plan 可为每个读取步骤声明 `sourceTable`（当前 schema 中的语义表槽，
如 `orders` 或 `complaints`）。编译器只在该槽属于本次工作区、且工具参数契约为
`tableId + page + pageSize` 时，将其绑定为 `workspaceTable`；执行前再解析成当前
随机生成的 table ID。它不携带旧 workspace ID、记录 ID、筛选条件或业务结果。BM25
仍提供一般候选；对已经显式声明并通过 schema 校验的 `sourceTable`，当前工作区的
分页读取工具可作为确定性候选，避免中英文表字段术语没有字面重合时错误退回。
未知表槽或无法绑定的参数失败关闭并交回模型。

`workspace-workpack-online-precheck-v2` 曾使用冻结工作包的受限读取前缀。它虽然经过
同一上传解析和 `TaskRunner`，但该前缀会把任务资产的表选择结构预先注入 RSI 冷启动，
因此只保留为诊断工件，不能用于本设计的严格在线学习结论。后续 `v3` 预检取消该路径：
Baseline 和 RSI 都从同一个用户工作请求、Planner、工具检索、图编译与执行入口开始。

## 3. 文件与安全协议

每个工作区保存于 `artifacts/workspaces/<workspaceId>/`，不入 Git。用户可见的
`inputs/` 保存原始附件，`requests/` 保存每次已提交的问题文本，`exports/` 保存可下载结果；
内部的 `workspace.json`、`tables.json` 和草稿进入 `.rsi/`。上传限制为最多 10 个文件、
单文件 20 MiB、10,000 数据行/表、100 列/表；超限会返回错误。旧根目录 JSON 与 `sources/`
布局仍可恢复，但恢复过程不会迁移或改写用户已有文件。

- CSV：UTF-8/UTF-8-SIG 解析；JSON：数组对象或单对象；TXT：逐行表。
- XLSX：只读取单元格的已保存值，不加载宏、不执行公式或文件中的指令；若运行环境
  未安装安全的 XLSX 读取依赖，明确报告该格式暂不可用，CSV/JSON/TXT 不受影响。
- 每行有稳定 `rowId = sourceId:sheet:sourceRow`；证据为
  `workspace:<workspaceId>:<sourceId>:<sheet>:<sourceRow>`。替换/删除源文件会使
  依赖它的后续任务失效，而不会复用旧业务值。
- 文件内容只作为数据经工具返回。模型系统提示明确禁止把文件内文字当作指令。

## 4. 工具目录

第一版提供 18 个有独立职责的受限工具：

1. `workspace_list_sources`
2. `workspace_get_schema`
3. `workspace_profile_table`
4. `workspace_preview_rows`
5. `workspace_get_row`
6. `workspace_filter_rows`
7. `workspace_sort_rows`
8. `workspace_join_rows`
9. `workspace_aggregate_rows`
10. `workspace_compare_tables`
11. `workspace_search_text`
12. `workspace_find_evidence`
13. `workspace_get_policy_excerpt`
14. `workspace_get_task_context`
15. `workspace_list_saved_reports`
16. `workspace_save_draft`
17. `workspace_export_csv`
18. `workspace_publish_report`

所有参数使用 JSON Schema，工具标注 `read`、`compute` 或 `artifact`。没有
`analyze_everything`、隐藏 LLM 分析、shell、SQL 或文件执行工具。批量结果有硬上限；
大表必须分页、筛选、关联或聚合后再送回模型。

## 5. 工作请求、澄清与成果

创建请求会记录角色、自然语言目标、当前资料表/列摘要和可选上一个报告 ID。
若没有资料，或请求显式要求跨期资料/规则资料但对应表或政策文本不存在，API 返回
确定性澄清项；澄清本身不调用模型。开始运行需要显式费用确认，并可取消。

用户工作没有可靠 gold 时，`workspace_publish_report` 将状态标为
`user_review_required`，保留报告、筛选清单、证据和待核查项，但不把“运行结束”
提升为训练经验。预定义工作包会附带私有、声明式规则校验；通过才为 `passed`。
报告与 CSV 导出只进入当前工作区，可在同一工作区继续追问并将上一个报告作为只读
上下文工具返回。

## 6. 新工作包资产

`benchmarks/workpacks-v1.json` 冻结三场景共 72 个工作请求：每场景 4 个工作流
类型，每类型 6 个不同实例，划分为 4 train、1 validation、1 test。工作包资料由
冻结的公开来源记录重组为可下载/可拖入的 CSV、JSON、TXT 文件，并经过和用户上传
完全相同的解析器及工具入口。

| 场景 | 四类工作流 |
|---|---|
| 财务 | 订单-支付-退款核对；取消/分期风险队列；期间金额与异常贡献；缺失关联/重复核查 |
| 客服 | 渠道/产品/响应健康；叙述与延迟升级队列；企业响应与政策草稿；两期投诉变化比较 |
| 技术工单 | 未分派/里程碑/时效分诊；标签/正文阻塞摘要；活动与评论跟进；双导出变更比较 |

每项记录其原始公开来源、重组文件、人工规则/政策和任何注入异常。CFPB 叙述只标为
消费者公开陈述；GitHub Issues 只标为公开 issue，不称企业内部工单。工作包 manifest
及 split 在运行前冻结，Agent 看不到 private validator 或答案。

## 7. 在线预检、成本和饱和规则

串行固定 `run_limit=model_limit=read_limit=1`。预检在每场景选择两个工作流、每类两条
连续 train，共 12 个任务；Baseline 与 RSI 各运行同一顺序，RSI 从全新空经验库开始。
以 V4 的历史实际均值做**执行前估算**：约 24 次 Agent、约 120 次模型请求、约
0.33M Agent token；没有可靠单价配置时不虚构美元。若完成后再做双顺序 Judge，最多
额外 24 次 Judge 请求，费用和 token 单列。用户工作台单次运行的实际成本由 UI 的
费用确认和保存 usage 展示；不会在本轮静默发起 paid run。

预检只有在以下条件全部满足时才扩展：文件隔离和证据定位正确；train 更新无维护错误；
同 workflow 的后续任务确实读取已保存经验；硬校验通过；恢复有界；计量完整。任何
影响 runtime、提示、预算或解析器的变更建立新实验 ID，旧记录只保留为诊断。

饱和检查在看结果前固定：按每个场景/工作流的连续 4 个 train 前缀作为窗口；若相邻
两个窗口的累计 token 节省率变化绝对值小于 3 个百分点、Fast 覆盖变化小于 10 个
百分点且成功率变化为 0，则标记“本有限池可能进入平台期”。四条 train 不足以形成
两个窗口时必须报告“样本不足，不能判断”。它是描述性检查，不证明理论上限。

## 8. 验收与展示

本轮本地验收先覆盖三场景各一个工作区的 CSV/JSON/TXT 路径、XLSX 可用性状态、
隔离、删除/替换、证据定位、无用户学习、schema 不匹配回退、取消和有界恢复。
浏览器工作台展示当前计划、模型事件、结构化图/绑定事件、工具观察、报告、清单、
下载和历史 replay；实验中心单列真实在线曲线、经验来源/使用、恢复和平台期结论。
图表只读取保存结果，不能写死收益或虚构 G1/G2。
