# 项目状态快照

更新时间：2026-09-10。功能基线 `9520ae7`；本快照所在的文档提交在其后，实际 HEAD 以 `git log -1` 为准。

- 项目：RSI 数字员工 Lab。
- 仓库：`/Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab`。
- 当前分支：`feat/graph-rsi`。不要在父目录误建第二个仓库。
- 协作：原 session 作为讨论 session，用户将另建执行 session。当前未替用户新建任务，没有安排自动化。
- 读取顺序：`AGENTS.md` → `docs/ARCHITECTURE.md` → `docs/DESIGN_DECISIONS.md` → `docs/EXPERIMENT_STATUS.md` → `docs/TODO.md`。
- 本轮已实现筛选后补查 Motif，待本地提交；磁盘运行记录在本轮结束时无 queued/running 项。旧 `4317` 服务不是热重载，`f6d572dd` 使用旧代码但保留原始轨迹；本轮证据使用当前代码的 `4318` 临时服务，已完成后应停止。

## 已完成

任务库300任务，Python runtime，强基线/Plan基线/AutoTool/Graph RSI，在线图版本，冻结成对评测，真实执行可视化与回放，共用业务报告，匿名双顺序 LLM Judge（0–10维度分、0–1 reward）。本轮在现有 dict runtime 增加 Plan 语义接口 `selection` 与 `foreach.filter` Motif、`plan_react_reuse` 对照、前端来源/绑定/执行/修订展示。详细边界和实验数字见 [motif-filter-then-enrich-validation-2026-09-10.md](../docs/motif-filter-then-enrich-validation-2026-09-10.md)。

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

清理前为104个Python测试；旧沙箱专用测试移除，共用协议测试改用注入工具。本轮为64个Python测试、4个前端回放测试、类型检查和构建通过；300条契约校验（10,400 次工具调用、0 次模型调用）通过。本轮模型正常 train 证据：`b5abdd11` 冷启动保存 Motif G0，`fa813841` 热启动复用，`7c32fa3e` 为不回写经验的复用 Plan ReAct 对照；均通过结构化评分。

## 配置与私有状态

根 `.env` 已有用户配置，不读取/打印密钥，不覆盖文件。执行角色 `LLM_*`；规划 `PLANNER_*`；裁判 `JUDGE_*`，后两者未填时继承执行配置；HTTP全部经 `model_client.py`，thinking=false。最近实验为qwen/qwen3.5-27b，不代表以后配置不变。

本地不入Git的证据：

- `artifacts/taskbank/records.sqlite3`、`gold.json`：冻结记录/仅供硬评分的参考答案。
- `artifacts/taskbank-runs/<id>.json`：原始运行。
- `artifacts/online-graphs.json`：原三份 G0 加 finance/cancelled_payments Motif G0 `b13e00e4` 与证据。
- `artifacts/paired-evaluations/<id>.json`、`sources/`：成对实验与新实验源码快照。
- `artifacts/llm-judgements/<id>.json`、`inputs/`：裁判与输入。

在新机器或 worktree 中这些文件不一定存在。先核查，不静默重造数据或复制凭据。Linux需要时用户已允许 `ssh v100`；当前任务库可在本地运行。ERPNext/Zammad是另一条已部署的只读平台路径，连接状态需现场检查。

## 下一步

执行入口见 `docs/EXECUTION_HANDOFF.md`。下一项应冻结当前 Motif/Plan 版本，运行已实现的 `plan_react_reuse` 对照评测并保留全部结果；之后才可进行最终 test，test 反馈不得回写 Motif。

每阶段结束更新本文件的基线、在途任务、验证结果和下一步；它是普通 Markdown 快照，没有自动 `.save_state` 命令。

平台恢复记录：远端 v100 容器运行正常，本地18080/18081隧道曾缺失；本轮已重新建立SSH转发。隧道属于进程状态，新session应核查，不能假定永久存活。

本轮恢复后 `npm run platforms` 检查 ERPNext/Zammad 均 reachable（只读端点），没有重新部署或重置远端数据库。
