# 项目状态快照

更新时间：2026-09-10。功能基线 `9520ae7`；本快照所在的文档提交在其后，实际 HEAD 以 `git log -1` 为准。

- 项目：RSI 数字员工 Lab。
- 仓库：`/Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab`。
- 当前分支：`feat/graph-rsi`。不要在父目录误建第二个仓库。
- 协作：原 session 作为讨论 session，用户将另建执行 session。当前未替用户新建任务，没有安排自动化。
- 读取顺序：`AGENTS.md` → `docs/ARCHITECTURE.md` → `docs/DESIGN_DECISIONS.md` → `docs/EXPERIMENT_STATUS.md` → `docs/TODO.md`。
- 旧 `online-e2e-train-v1` 保留为负收益历史。修复后 RSI-only `online-rsi-graph-precheck-v3` 为 36/36、386,813 token、30 次 Fast 复用、0 维护错误；新 Baseline `online-rsi-graph-matched-v4` 为 32/36、509,630 token。分时匹配记录下 RSI token -24.1%，未达到 30% 目标，详情见 `docs/online-rsi-matched-results-2026-09-10.md`。运行 artifacts 不入 Git。

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

页面：`/#demo`、`/#evaluation`、`/#evolution`、`/#taskbank`、`/#platforms`（开发基址 `http://127.0.0.1:5173`）。FastAPI文档：`http://127.0.0.1:4317/docs`。

清理前为104个Python测试；旧沙箱专用测试移除，共用协议测试改用注入工具。本轮为67个Python测试、4个前端回放测试、类型检查和构建通过；300条契约校验（10,400 次工具调用、0 次模型调用）通过。真实 train 尝试 `800f792f`、`9ef504a8`、`acfa3b5e`、`504f58d7`、`982d7e44` 未 materialize 可组合 TinyEdge：保留编译歧义/模型超时/网络失败，不声称 Composition 收益。

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

当前可展示结论是在线经验积累与 Fast 复用，并在五个 family 降低成本；`cancelled_payments` 是真实负收益，30% 全量目标未达到。下一项只能从这个负收益和 Baseline evidence 覆盖失败提出正常 train 假设；不得重跑本轮任务直到结果好看，冻结方案前不扩展 validation/test，test 反馈不得回写 Workflow/TinyEdge。

每阶段结束更新本文件的基线、在途任务、验证结果和下一步；它是普通 Markdown 快照，没有自动 `.save_state` 命令。

平台恢复记录：远端 v100 容器运行正常，本地18080/18081隧道曾缺失；本轮已重新建立SSH转发。隧道属于进程状态，新session应核查，不能假定永久存活。

本轮恢复后 `npm run platforms` 检查 ERPNext/Zammad 均 reachable（只读端点），没有重新部署或重置远端数据库。
