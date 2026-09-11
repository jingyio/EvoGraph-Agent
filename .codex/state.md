# 项目状态快照

更新时间：2026-09-11。功能基线 `9520ae7`；本快照所在的文档提交在其后，实际 HEAD 以 `git log -1` 为准。

- 项目：RSI 数字员工 Lab。
- 仓库：`/Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab`。
- 当前分支：`feat/graph-rsi`。不要在父目录误建第二个仓库。
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

主展示页面（开发基址 `http://127.0.0.1:5173`）：`/#home` 是单一企业运营数字员工的主工作台；财务、客服、研发运营是其业务能力而非三个产品。页面从业务需求、已保存工作记录回放、RSI 结构化运行时和 HTML 业务简报开始，不显示任务 ID 或 `train`/benchmark 语言。主工作台只读最终 V4 DTO，不发模型请求、不改变经验或实验；财务 `cents` 指标仅在展示层格式化为 BRL，原始整数仍在报告与回放中可审计。旧 `/#employees` 会重定向至 `/#home`。`/#compare` 默认全量 36 个同任务对比并聚合为财务/客服/技术工单各12项。三领域播放器按保存事件的实际索引逐步前进（不按不同轨迹长度比例抽帧），可切换领域聚焦轨道，并显示累计 LLM/token/工具/时间和 M（模型）/S（结构化运行时）/C（控制）事件。`/#insights` 为 RSI 效果与严格报告审计；`/#replay?task=finance-cancelled_payments-02` 会区分模型调度工具、图执行器调度工具、当前观察参数绑定、筛选和活跃 DAG 节点。技术 `unassigned` 未从任何汇总删除，但不作主讲回放。公开历史数据经本地 SQLite + 强 JSON Schema 的只读工具暴露，不能称生产企业写入部署。旧工作台仍在 `/#demo`、`/#evaluation`、`/#evolution`、`/#taskbank`、`/#platforms`。FastAPI 文档：`http://127.0.0.1:4317/docs`。
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

当前可展示结论是在线经验积累与 Fast 复用：六个 family 均在最终严格串行 V4 中降低 token，全量达到 -35.6%。这不证明多代结构进化、Composition 收益、独立 Judge 优势或通用低延迟。不要重跑该实验直到结果好看；若继续研究，必须建立新版本、固定新协议，validation/test 反馈不得回写 Workflow/TinyEdge。

2026-09-11 收口补记：`online-rsi-all-train-saturation-v3` 的 30-family 首到达任务结果可受限展示（RSI token `-18.48%`、模型请求 `-28.73%`），但其 `runtimeOverhead` 含约 14.3 秒被误分类的 Composition 模型等待，不能用于 overhead 结论或与 V4 合并。`#live` 已支持真实、可保存回放的 Baseline/RSI 对照；启动必须显式费用确认，单任务为两次 Agent、两任务为四次 Agent，且后端拒绝并行 live 会话。预算暂停期间不发起额外模型调用，使用保存会话录制。

2026-09-11 展示叙事收口：原 `#employees` 三岗位卡已撤回，改为 `#home` 单一企业运营数字员工工作台，旧链接重定向。财务分析、客服分析、研发运营是可切换能力；首屏只展示业务需求、保存的真实工作记录、模型与 RSI 运行时差别、业务指标和完整 HTML 简报入口。36 个案例、原始任务 ID、审计和边界移至 `#compare`、`#insights` 与 `#replay`。工作台只读取最终 V4 DTO 和已有报告，没有新增 Agent/Judge/学习调用，也不把 HTML 报告称为 PPTX 或生产部署。验证：`npm test` 99 passed、`npm run test:frontend` 4 passed、`npm run build` passed、`git diff --check` passed；浏览器确认财务能力显示真实 Fast 流程的 RSI 运行时载入、同任务对照与格式化业务金额，且不显示 task ID/train/benchmark 语言。

每阶段结束更新本文件的基线、在途任务、验证结果和下一步；它是普通 Markdown 快照，没有自动 `.save_state` 命令。

平台恢复记录：远端 v100 容器运行正常，本地18080/18081隧道曾缺失；本轮已重新建立SSH转发。隧道属于进程状态，新session应核查，不能假定永久存活。

本轮恢复后 `npm run platforms` 检查 ERPNext/Zammad 均 reachable（只读端点），没有重新部署或重置远端数据库。
