# 项目状态快照

更新时间：2026-09-10。功能基线 `9520ae7`；本快照所在的文档提交在其后，实际 HEAD 以 `git log -1` 为准。

- 项目：RSI 数字员工 Lab。
- 仓库：`/Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab`。
- 当前分支：`feat/graph-rsi`。不要在父目录误建第二个仓库。
- 协作：原 session 作为讨论 session，用户将另建执行 session。当前未替用户新建任务，没有安排自动化。
- 读取顺序：`AGENTS.md` → `docs/ARCHITECTURE.md` → `docs/DESIGN_DECISIONS.md` → `docs/EXPERIMENT_STATUS.md` → `docs/TODO.md`。
- 本轮已完成隔离的 36-task 在线训练对照 `online-e2e-train-v1`，源码提交见后续 Git log；运行 artifacts 不入 Git。临时验证服务 `4320` 已停止。旧 `4317` 服务不是热重载，不能用它验证新路径。

## 已完成

任务库300任务，Python runtime，强基线/Plan基线/AutoTool/Graph RSI，在线图版本，冻结成对评测，真实执行可视化与回放，共用业务报告，匿名双顺序 LLM Judge（0–10维度分、0–1 reward）。本轮在现有 dict runtime 加入 Persistent TinyEdge 规范化 identity、train-only 连续读取片段挖掘、Fast/Composition/Fallback 路由、composition 模型角色和片段来源/绑定/执行 UI；不做 Transient TinyEdge Group。详细边界和实证见 [g-agent-local-composition-design-2026-09-10.md](../docs/g-agent-local-composition-design-2026-09-10.md) 与 [g-agent-local-composition-validation-2026-09-10.md](../docs/g-agent-local-composition-validation-2026-09-10.md)。

本轮追加最小 AutoTool：`backend/tool_inertia.py` 持久化模型来源、通过评分的 train 串行工具路径与无业务值参数契约；`motif_first` 在 `defer` 读取交接处至多尝试一次只读惯性调用，`motif_only` 是关闭对照。真实预检三条 train 均通过，`motif_first` 一次尝试因 CIPS 0.1348 低于 0.55 拒绝，未实际调用工具、未观察到收益；并发批不形成惯性上下文。详情见 [autotool-inertia-design-2026-09-10.md](../docs/autotool-inertia-design-2026-09-10.md)。

本轮端到端在线实验固定 36 个不同 train 实例，基线 `plan_react` 不学习、RSI `motif_first` 从独立空经验串行更新。实际结果：基线 36/36、601,435 token、737.62s；RSI 35/36、766,076 token、890.26s。唯一 RSI 失败为 `finance-installments-06` 的绑定歧义恢复后模型预算耗尽。历史图由 `support-channels-01` 产生并在后续五条同 family 任务 Fast 复用，确实省掉完整 Plan；Composition、TinyEdge 和 AutoTool 运行时调用均未触发。Judge 为同一模型，36 对双顺序额外 339,938 token，平均 reward 两臂同为 0.9714。完整结论、失败和审计修复见 [online-e2e-train-results-2026-09-10.md](../docs/online-e2e-train-results-2026-09-10.md)。

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

页面：`/#demo`、`/#evaluation`、`/#evolution`、`/#taskbank`、`/#platforms`（开发基址 `http://127.0.0.1:5173`）。FastAPI文档：`http://127.0.0.1:4317/docs`。

清理前为104个Python测试；旧沙箱专用测试移除，共用协议测试改用注入工具。本轮为67个Python测试、4个前端回放测试、类型检查和构建通过；300条契约校验（10,400 次工具调用、0 次模型调用）通过。真实 train 尝试 `800f792f`、`9ef504a8`、`acfa3b5e`、`504f58d7`、`982d7e44` 未 materialize 可组合 TinyEdge：保留编译歧义/模型超时/网络失败，不声称 Composition 收益。

## 配置与私有状态

根 `.env` 已有用户配置，不读取/打印密钥，不覆盖文件。执行角色 `LLM_*`；规划 `PLANNER_*`；裁判 `JUDGE_*`，后两者未填时继承执行配置；HTTP全部经 `model_client.py`，thinking=false。最近实验为qwen/qwen3.5-27b，不代表以后配置不变。

本地不入Git的证据：

- `artifacts/taskbank/records.sqlite3`、`gold.json`：冻结记录/仅供硬评分的参考答案。
- `artifacts/taskbank-runs/<id>.json`：原始运行。
- `artifacts/online-graphs.json`：已有图版本、`workflows` / `tinyEdges` 和 schema 3 的 `toolInertia`；TIG 仅保存路径/参数契约，不保存旧业务值。
- `artifacts/paired-evaluations/<id>.json`、`sources/`：成对实验与新实验源码快照。
- `artifacts/llm-judgements/<id>.json`、`inputs/`：裁判与输入。

在新机器或 worktree 中这些文件不一定存在。先核查，不静默重造数据或复制凭据。Linux需要时用户已允许 `ssh v100`；当前任务库可在本地运行。ERPNext/Zammad是另一条已部署的只读平台路径，连接状态需现场检查。

## 下一步

在线实验未显示总体收益，默认保持 AutoTool 关闭。下一项应以 `finance-installments-06` 的绑定歧义、Composition 覆盖不足和局部 Fast 命中未摊销为明确问题，先在正常 train 流量中修复/积累证据；不得重跑本轮任务直到结果好看，冻结方案前不扩展 validation/test，test 反馈不得回写 Motif/TinyEdge/TIG。

每阶段结束更新本文件的基线、在途任务、验证结果和下一步；它是普通 Markdown 快照，没有自动 `.save_state` 命令。

平台恢复记录：远端 v100 容器运行正常，本地18080/18081隧道曾缺失；本轮已重新建立SSH转发。隧道属于进程状态，新session应核查，不能假定永久存活。

本轮恢复后 `npm run platforms` 检查 ERPNext/Zammad 均 reachable（只读端点），没有重新部署或重置远端数据库。
