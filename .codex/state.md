# 项目状态快照

更新时间：2026-09-13。功能基线 `9520ae7`；本快照所在的文档提交在其后，实际 HEAD 以 `git log -1` 为准。

- 项目：RSI 数字员工 Lab。
- 仓库：`/Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab`。
- 当前分支：`feat/graph-rsi`。不要在父目录误建第二个仓库。
- 2026-09-13 Workpack V17 full 已完成：`005ffeb9-964e-42ac-86e9-fb9e8f2212fe` 的 mode
  名为 `full_train_v15`，但运行时修订线是 V17，不能与旧 V15 cancelled full 混淆。48 个
  冻结 train 工作包、两臂各48次、串行 `run=model=read=1`，两臂均48/48私有结构化事实与
  证据通过且 usage 完整。Baseline/RSI token 2,244,017→1,243,546（**-44.5839%**），模型
  请求258→149，工具422→325；RSI形成12个Workflow，后续Fast35次、Fallback13次、
  Composition0。报告恢复、工具拒绝/错误和本地开销均保留，详情见
  `docs/workspace-workpack-v17-full-results-2026-09-13.md`。旧V15 full `6c56245b` 仍是
  pair2 transport retry usage未知的取消诊断，绝不覆盖或拼接。
- 2026-09-13 交付验收完成：默认 `/#home` 通过实际三岗位工作区运行验证了资料加载、任务、
  真实 Agent、同 run 轨迹、HTML 下载和同工作区追问。财务主任务/追问为
  `dfb877a2`/`136ef9c8`，客服为 `a2886561`/`4d307152`，技术工单为
  `d16052ad`/`2807d3ae`；六个 run 均完成、usage 完整、各一次报告。客服主任务保留
  3 次工具错误/拒绝，不能写成零错误。`/#experiments` 首屏改用轻量实验 DTO：列表约
  29,869 B，V17 摘要约 290,393 B；原始图、观察、Plan 和报告仍须从单 run 接口按需读取。
  HTML 下载接口均返回 `Content-Disposition: attachment`，不会另做示例数据或伪造进度。
- 2026-09-13 Workpack V14 在途：V13 财务一对多对账已通过，但客服 Baseline 暴露
  `count + groupBy` 静默返回总行数、被误作不同分组数的问题。V14 明确拒绝该调用并要求
  `group_count`，重新从隔离 smoke 开始。V13 结果 `5dbcb2fc` 为 2/3 vs 3/3，保留诊断，
  不得主张其 token 差。V13 此前确认财务订单行按业务键对账时被错误要求唯一，
  已改为唯一键计算加完整行级证据；`model_client.py` 已对短暂传输失败增加一次有界重试，
  分别记录逻辑模型请求、实际 provider attempts、retry 与 usage 不完整。V13 是独立
  staged runtime，先运行 smoke；协议见
  `docs/workspace-workpack-v13-repair-protocol-2026-09-13.md`，不得与 V12 混接。
- 2026-09-13 Workpack V12：V11 Fast 路径的重复确定性 compute 长尾已用两臂共享
  guard 修复，并通过 smoke `2413c09a`（3/3）与 precheck `587d7c50`（12/12）。
  full `f8acd9e2` 为 Baseline 42/48、RSI 46/48；表面 token 1,813,753→1,078,947
  （-40.513%）因质量门槛失败且末尾两臂共同网络失败，只能作诊断。RSI 有12个 G0、
  36次 Fast、0 Composition、0维护错误；详情见
  `docs/workspace-workpack-v12-results-2026-09-13.md`，不得与 V4 主结论拼接。
- 协作：原 session 作为讨论 session，用户将另建执行 session。当前未替用户新建任务，没有安排自动化。
- 读取顺序：`AGENTS.md` → `docs/ARCHITECTURE.md` → `docs/DESIGN_DECISIONS.md` → `docs/EXPERIMENT_STATUS.md` → `docs/TODO.md`。
- 最终主证据是严格串行 `online-rsi-serial-final-v4`：固定 36 个不同 train 任务、独立空 RSI 经验、`run_limit=model_limit=read_limit=1`、同 session 交替运行。Baseline/RSI 均 36/36；Agent token 539,468→347,368（**-35.6%**），模型请求 203→114，工具 274→277。RSI 形成 6 个 G0，后续实际 Fast 复用 24 次；无 Composition、无 G1/G2。全部 Agent usage 完整、工具/维护错误均为0；Judge 26/36完成、10个服务超时、同模型且15个顺序分歧。详见 `docs/online-rsi-serial-final-results-2026-09-11.md`。运行 artifacts 不入 Git。
- 旧 `online-e2e-train-v1` 保留为负收益历史；`online-rsi-graph-matched-v4` 保留为分时匹配且 token -24.1% 的历史对照，不能与最终 V4 拼接。`cancelled_payments` 的编译器语义/等价读取修复在 V4 的严格对照中转正为 -44.0%。规模补验为 `efficiency-scale-serial-v4`，读取峰值固定为1，不主张并发收益。

## 已完成

任务库300任务，Python runtime，强基线/Plan基线/AutoTool/Graph RSI，在线图版本，冻结成对评测，真实执行可视化与回放，共用业务报告，匿名双顺序 LLM Judge（0–10维度分、0–1 reward）。本轮在现有 dict runtime 加入 Persistent TinyEdge 规范化 identity、train-only 连续读取片段挖掘、Fast/Composition/Fallback 路由、composition 模型角色和片段来源/绑定/执行 UI；不做 Transient TinyEdge Group。详细边界和实证见 [g-agent-local-composition-design-2026-09-10.md](../docs/g-agent-local-composition-design-2026-09-10.md) 与 [g-agent-local-composition-validation-2026-09-10.md](../docs/g-agent-local-composition-validation-2026-09-10.md)。

AutoTool/TIG 惯性执行已退役；保留 `backend/autotool.py` 的 BM25、参数契约和历史轨迹兼容，但不再调优触发或把历史拒绝写成收益。

修复后对照复用 RSI-only 的完整原始运行，检查 frozen manifest、36 条成功/usage、空经验与 train-only 顺序、模型名、预算、工具契约、任务哈希和 runtime revision 后，在新目录仅补跑 Baseline。Baseline 四个 `cancelled_payments` 样本有 `evidence_coverage` 有界失败；RSI 36/36。六个 G0 首次保存后实际被后续各五条同 family 任务使用；没有 G1/G2 或 Composition。Judge 72 请求、336,757 token，平均 reward Baseline/RSI 0.9768/0.9746，但同模型且 18 对顺序分歧，不作质量优劣证明。

最近功能提交：`9520ae7` Judge/reward/Plan对照；`e9e9df1` 强基线评测/报告；`e15d7c1` 执行回放；`f50d97d` 在线图进化。

## 环境与检查

```bash
git status --short
git log -3 --oneline
npm test
npm run test:frontend
npm run build
```

已有 `.venv`，前端 Node 22+。后端 `npm run dev:backend` 或 `.venv/bin/python -m backend serve`（4317），前端 `npm run dev:frontend`（5173）。启动前检查端口，避免重复服务；重启前确认没有在途模型任务。

主展示页面（开发基址 `http://127.0.0.1:5173`）：`/#home` 是交互式企业运营数字员工工作台；财务、客服、研发运营是同一员工的业务能力。页面支持 CSV/XLSX/JSON/TXT 上传、资料预览、确定性澄清、费用确认后的真实 Agent、同 run 的 DAG/模型/结构化/工具轨迹、HTML报告下载、导出、追问和历史工作。普通用户工作区使用独立存储且 `learning_enabled=False`，不会污染实验经验；追问只加载同工作区父报告的公开摘要，仍需本次观察证据。`/#experiments` 默认展示保存的 V17 48-task 结果和同族经验使用；`/#compare`、`/#insights`、`/#replay` 保留 V4 历史审计。公开历史数据经本地 JSON Schema 的只读工具访问，不能称生产企业写入部署。FastAPI 文档：`http://127.0.0.1:4317/docs`。
- 展示 API `GET /api/showcase/online-rsi-serial-final-v4` 和任务细节 `GET /api/showcase/online-rsi-serial-final-v4/pairs/{taskId}` 只读地从最终 V4 artifact 派生 DTO。它使用 gold 计算 audit，但不返回 gold、不调用模型、不改写 artifact：两臂结构化精确检查均 36/36；加上已知 ID、可追溯数字和金额单位措辞的有限摘要审计为 Baseline 25/36、RSI 26/36。后者不是全面自然语言事实判定。

清理前为104个Python测试；旧沙箱专用测试移除，共用协议测试改用注入工具。当前为92个Python测试、4个前端回放测试、类型检查和构建通过；展示 API/严格审计/事件执行来源的协议回归已覆盖。300条契约校验（10,400 次工具调用、0 次模型调用）通过。真实 train 尝试 `800f792f`、`9ef504a8`、`acfa3b5e`、`504f58d7`、`982d7e44` 未 materialize 可组合 TinyEdge：保留编译歧义/模型超时/网络失败，不声称 Composition 收益。

## 配置与私有状态

根 `.env` 已有用户配置，不读取/打印密钥，不覆盖文件。执行角色 `LLM_*`；规划 `PLANNER_*`；裁判 `JUDGE_*`，后两者未填时继承执行配置；HTTP全部经 `model_client.py`，thinking=false。最近实验为qwen/qwen3.5-27b，不代表以后配置不变。

本地不入Git的证据：

- `artifacts/taskbank/records.sqlite3`、`gold.json`：冻结记录/仅供硬评分的参考答案。
- `artifacts/taskbank-runs/<id>.json`：原始运行。
- `artifacts/online-graphs.json`：已有图版本、`workflows` / `tinyEdges` 与历史兼容字段；不再更新或执行 TIG 惯性动作。
- `artifacts/paired-evaluations/<id>.json`、`sources/`：成对实验与新实验源码快照。
- `artifacts/llm-judgements/<id>.json`、`inputs/`：裁判与输入。

在新机器或 worktree 中这些文件不一定存在。先核查，不静默重造数据或复制凭据。Linux需要时用户已允许 `ssh v100`；当前任务库可在本地运行。ERPNext/Zammad是另一条已部署的只读平台路径，连接状态需现场检查。

## 下一步

2026-09-12 在途工作：新增交互式工作区/三场景 Workpack 运行路径后，V6 预检发现
Baseline 的公开资料范围恢复缺陷，故 V6 不可用于同质量成本结论。V7 的公开
`requiredTableSlots` 确定性恢复已回归并实际运行 Smoke `59892bb0-66ab-4d7f-93b9-0ee7dc8e95e4`：
Baseline 3/3，RSI 1/3，故 V7 不可作为同质量成本结论。财务 RSI 已读取正确资料却模型手工
汇总错误；技术 RSI 是人工停止后的取消，成本和失败 artifact 均保留。

当前工作树新增 V8 共享确定性键控对账能力 `workspace_reconcile_keyed_sums`：只接受当前
工作区表/字段/键/别名/阈值并回传证据，不访问私有验收或自动改写报告。两臂同样可用，故
V8 是新的独立 staged runtime。Smoke `57c295a5-d7d9-4a22-b77c-d1893fef696f` 为 6/6；
预检 `31313718-fb89-491f-81d5-9ee7cb925433` 为 24/24，RSI token 比 Baseline 高10.0%，
但已验证财务实际调用对账工具、5 个 G0 形成和4次 Fast 复用。预检中的3次 schema/tool
拒绝与4次一次性公开范围恢复均可审计，没有维护错误或无界循环；正式 V8 train 将在不改
runtime 的前提下执行。详见 `docs/workspace-workpack-v8-reconciliation-protocol-2026-09-12.md`。
旧 V5/V6/V7 artifacts 保留。

当前可展示结论是在线经验积累与 Fast 复用：六个 family 均在最终严格串行 V4 中降低 token，全量达到 -35.6%。这不证明多代结构进化、Composition 收益、独立 Judge 优势或通用低延迟。不要重跑该实验直到结果好看；若继续研究，必须建立新版本、固定新协议，validation/test 反馈不得回写 Workflow/TinyEdge。

2026-09-11 收口补记：`online-rsi-all-train-saturation-v3` 的 30-family 首到达任务结果可受限展示（RSI token `-18.48%`、模型请求 `-28.73%`），但其 `runtimeOverhead` 含约 14.3 秒被误分类的 Composition 模型等待，不能用于 overhead 结论或与 V4 合并。`#live` 已支持真实、可保存回放的 Baseline/RSI 对照；启动必须显式费用确认，单任务为两次 Agent、两任务为四次 Agent，且后端拒绝并行 live 会话。预算暂停期间不发起额外模型调用，使用保存会话录制。

2026-09-11 展示叙事收口：原 `#employees` 三岗位卡已撤回，改为 `#home` 单一企业运营数字员工工作台，旧链接重定向。财务分析、客服分析、研发运营是可切换能力；首屏只展示业务需求、保存的真实工作记录、模型与 RSI 运行时差别、业务指标和完整 HTML 简报入口。36 个案例、原始任务 ID、审计和边界移至 `#compare`、`#insights` 与 `#replay`。工作台只读取最终 V4 DTO 和已有报告，没有新增 Agent/Judge/学习调用，也不把 HTML 报告称为 PPTX 或生产部署。验证：`npm test` 99 passed、`npm run test:frontend` 4 passed、`npm run build` passed、`git diff --check` passed；浏览器确认财务能力显示真实 Fast 流程的 RSI 运行时载入、同任务对照与格式化业务金额，且不显示 task ID/train/benchmark 语言。

每阶段结束更新本文件的基线、在途任务、验证结果和下一步；它是普通 Markdown 快照，没有自动 `.save_state` 命令。

平台恢复记录：远端 v100 容器运行正常，本地18080/18081隧道曾缺失；本轮已重新建立SSH转发。隧道属于进程状态，新session应核查，不能假定永久存活。

本轮恢复后 `npm run platforms` 检查 ERPNext/Zammad 均 reachable（只读端点），没有重新部署或重置远端数据库。
