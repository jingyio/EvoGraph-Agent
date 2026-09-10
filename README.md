# RSI 数字员工 Lab

Python/FastAPI 后端，React/TypeScript 前端。围绕财务、客服和技术工单，展示结构化图执行、Plan 复用、在线图改进、真实成本对照和报告质量评价。旧合成业务沙箱已移除。

## 新 session 从这里开始

| 文档 | 用途 |
|---|---|
| [AGENTS.md](AGENTS.md) | 项目约束和必读顺序 |
| [.codex/state.md](.codex/state.md) | 当前状态、环境、恢复入口 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 已实现架构与状态边界 |
| [DESIGN_DECISIONS](docs/DESIGN_DECISIONS.md) | 已确认的设计决策 |
| [EXPERIMENT_STATUS](docs/EXPERIMENT_STATUS.md) | 已有实验、局限、未证明事项 |
| [TODO](docs/TODO.md) | 下一阶段工作与验收标准 |
| [EXECUTION_HANDOFF](docs/EXECUTION_HANDOFF.md) | 可直接粘贴到执行 session 的交接提示 |

当前 session 负责讨论，用户另建执行 session。设计、代码与原始实验记录承接项目上下文，不要求继承整段聊天。

## 运行

已有环境使用 Python 3.9+、Node 22+，根目录 `.env` 存放用户模型配置，不能覆盖或提交。

```bash
npm run dev:backend
npm run dev:frontend
```

以上两个命令分别在两个终端运行：后端 4317、前端 5173。生产方式为 `npm run build` 后 `npm start`。新环境需先建立 `.venv`、安装 `requirements.lock.txt` 与 npm 依赖。

页面：[#demo](http://127.0.0.1:5173/#demo) 实时对照与回放；[#evaluation](http://127.0.0.1:5173/#evaluation) 冻结评测、报告与裁判；[#evolution](http://127.0.0.1:5173/#evolution) 在线版本；[#taskbank](http://127.0.0.1:5173/#taskbank) 任务与工具；[#platforms](http://127.0.0.1:5173/#platforms) ERPNext/Zammad 只读工作台。

## 模型与数据

执行配置 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`，规划配置 `PLANNER_*`，裁判配置 `JUDGE_*`；后两者缺省继承执行配置。HTTP 仅在 `backend/model_client.py`，关闭 thinking。没有独立角色模型时不声称大小模型协同或独立裁判。

任务库300任务来源为 Olist、CFPB、Zammad GitHub Issues，详见 [任务库](docs/taskbank.md)。任务由本项目设计，每类型指令高度重复、业务记录不同。参考答案仅供确定性评分。数据和运行记录在不入 Git 的 `artifacts/`，换机器/worktree前先检查是否可用。

ERPNext/Zammad 已有独立部署和读取连接器；平台种子记录由项目初始化，不等于真实企业生产数据。平台路径仍可使用 `npm run pipeline:platforms`，其中历史读取图有独立验证成本；不要与任务库无额外 rollout 的在线进化混淆。

## 验证与结果

```bash
npm test
npm run test:frontend
npm run build
npm run taskbank:validate
```

`taskbank:validate` 是工具契约/评分器校验，不是300次模型评测。实测指标与尚未证明的能力统一记录在 [EXPERIMENT_STATUS](docs/EXPERIMENT_STATUS.md)。详细机制见 [在线进化](docs/online-evolution.md)、[执行演示](docs/execution-demo.md)、[成对评测](docs/paired-evaluation.md)、[LLM Judge](docs/llm-judge.md)。

源码由 Git 管理；有日期的旧实验文档作为历史证据，不代表当前仍支持旧沙箱命令。
