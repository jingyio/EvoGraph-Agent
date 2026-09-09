# 数字员工 RSI Lab · Python 后端

React/TypeScript 展示界面 + Python/FastAPI Agent 后端，覆盖财务运营与客服运营。模型接口、业务工具、AutoTool、G-Agent 风格经验规划和 NetworkX 任务图均使用 Python。

后续端到端实验默认运行 `npm run pipeline:platforms`：直接读取已部署的 ERPNext/Zammad，依次执行 ReAct、学习读取图、Graph 复用与平台状态核对。当前实例仍是本项目初始化的演示记录，不能称为真实企业数据。合成 JSON 沙箱保留用于明确指定的回归实验，不再作为默认端到端环境。

TS 原型保存在 Git 提交 `e63b138`，当前工作树不再维护第二套后端。真实运行和历史验证结果不会因迁移被重写。

## 安装与启动

需要 Python 3.9+，Node 22+ 仅用于前端安装和构建。当前机器已创建 `.venv` 并安装依赖。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
npm install
npm run build
npm start
```

打开 <http://127.0.0.1:4317>。FastAPI 同时提供业务 API 和构建后的 React 页面；接口文档在 <http://127.0.0.1:4317/docs>。

```bash
npm test                 # Python pytest
npm run check            # Python 语法检查 + 前端类型检查
npm run build            # React 生产构建
npm run dev              # Python 后端热重载；前端改动后需重新 build
npm run demo -- --scenario finance
npm run demo -- --scenario support
npm run platforms
npm run verify:platforms
```

直接运行 Python 也可以：`.venv/bin/python -m backend serve`。

前后端独立开发：分别运行 `npm run dev:backend`（4317 API）和 `npm run dev:frontend`（5173 React）。在“递归进化实验”中启动独立的学习、验证、晋升闭环，详见 [递归进化范围与运行方式](docs/recursive-evolution.md)。

“负 Motif · 失败反思”支持从失败与修复轨迹中学习局部字段绑定经验；财务工作台可独立启用，详见 [负 motif 范围、使用和计量](docs/negative-motifs.md)。

“长程稳定性对照”按相同快照重复比较 ReAct、Graph 和 Graph＋负 motif，展示累计工具错误、任务状态与图执行归属，详见 [实验协议](docs/reliability.md)。

## 模型配置

填写项目根目录 `.env`。新环境可从 `.env.example` 复制；已有配置不应覆盖。

```dotenv
LLM_BASE_URL=https://你的服务基础地址/v1
LLM_API_KEY=服务端密钥
LLM_MODEL=服务实际支持的模型名
```

地址不要以 `/chat/completions` 结尾，程序会追加该路径。保存后重启服务。模型 HTTP 请求仅在 [backend/model_client.py](backend/model_client.py)，ReAct 和经验规划器通过注入接口使用同一客户端。

按用户要求，请求固定发送 `enable_thinking: false`；OpenRouter 同时发送 `reasoning.enabled: false`。模型请求开启多工具调用，提示模型把同一阶段互不依赖的读取、知识检索和已确定动作合并到一次响应；执行器仍按返回顺序逐项校验和执行。运行记录保存请求设置和供应商实际 reasoning token，未返回用量时不伪造为零。密钥不会返回浏览器或加入 Git。

## 运行方式

| 方式 | 行为 |
|---|---|
| 离线流程示例 | 固定程序驱动实际沙箱工具，验证业务闭环；0 次 LLM，不作为 RSI 性能结果 |
| 真实模型 ReAct | 模型选择工具、读取观察、继续执行；记录请求、token、工具错误和耗时 |
| Graph RSI | 从真实轨迹学习读取图，按当前数据绑定和执行；相似任务先进行经验选择，失败回退模型 |

命令行真实运行示例：

```bash
npm run demo -- --scenario finance --live --strategy graph --snapshot changed
```

`base` 是原始快照，`changed` 改变 ID、金额和记录数，`exception` 加入坐席不可用和付款归属冲突。数据在 `data/`，每次运行独立复制。

## 任务结果校验

执行器在模型结束后检查业务状态，有缺项时最多返回模型修正两轮，额外请求计入原有调用预算。预算、超时或取消后仍保存部分结果和校验信息。

- `auto`：预设任务检查岗位完整流程；自定义任务只检查状态约束，明确标记未验证任务完整性。
- `invariants`：检查超额分配、重复流水被分配、工单状态被改变、消息发送和坐席超载等。
- `finance_full`：额外检查可核验回款未分配、异常回款未登记、逾期事项缺失和报告缺失。
- `support_full`：额外检查草稿缺失、超时未升级、无合适负责人且未升级和报告缺失。

在界面的“结果校验目标”中可选择“岗位完整流程”。这会要求完成对应岗位任务，不适用于用户仅要求局部读取的任务。外部平台只读报告目前标记为 `not_evaluated`，需要独立事实评分。

`status=completed` 表示执行器正常结束，`evaluation.status=passed` 只证明所列业务状态规则通过，不能证明报告文字和因果解释完全正确。校验失败的运行不会自动晋升为新任务图。

## 任务图与 AutoTool

- [backend/autotool.py](backend/autotool.py)：从受控 OpenAPI 规格生成 7 个平台读取工具，校验参数、编码路径、提取响应；不生成任意代码或接受规格提供的目标主机。
- [backend/gagent.py](backend/gagent.py)：检索历史任务、让模型选择候选图与必要节点、补齐依赖；规划调用计入总数。
- [backend/graph.py](backend/graph.py)：从成功读取轨迹推断参数绑定、集合遍历和分页，使用 NetworkX 检查 DAG。
- [backend/graph_store.py](backend/graph_store.py)：影子读取验证、版本保存和适用性检查。

图仅复用第一次业务写入前的读取步骤。写入、草稿和报告继续由模型处理。图保存的是结构与参数来源，不缓存旧结果。学习本身无额外 LLM，但影子读取和源轨迹采集成本需单列与摊销。

Python 图使用新的实例/运行时指纹，保存在 `artifacts/graphs-python/`。旧 TS 图保留在原目录，不直接执行；可从同一历史真实运行重新学习并验证。已有运行的 JSON 和 Markdown 格式继续兼容前端。

## 外部业务环境

ERPNext 与 Zammad 已在 v100 独立部署；通过 SSH 隧道访问：

- ERPNext：<http://127.0.0.1:18080>
- Zammad：<http://127.0.0.1:18081>

Python 连接器支持真实分页、详情、证据引用和权限校验，当前全部只读。平台登录信息在被忽略的 `deploy/runtime/platform-access.json`。部署、隧道和备份见 [deploy/README.md](deploy/README.md)。

## 文件结构

```text
backend/model_client.py    唯一模型 HTTP 接口，关闭 thinking
backend/runtime.py         ReAct、图复用、预算、取消、缺项修正
backend/tools.py           沙箱业务规则与强 schema 校验
backend/connectors.py      ERPNext / Zammad 读取适配器
backend/evaluation.py      独立业务状态校验
backend/graph.py            NetworkX 任务图
backend/gagent.py           经验检索和节点选择
backend/app.py              FastAPI 与前端静态服务
src/                        React 工作台、图查看器、结果展示
shared/                     前端 TypeScript 类型
specs/                      平台 OpenAPI 与沙箱工具契约
data/                       合成业务快照与预设任务
tests_python/               Python 业务、协议、图和 HTTP API 测试
artifacts/                  运行、报告、图与验证结果（不提交）
```

详细的历史结果见 [Graph RSI 验证](docs/graph-rsi-validation-2026-09-09.md) 和 [平台验证](docs/platform-deployment-validation-2026-09-09.md)。这些是对应版本与配置的测量，不能当成当前 Python 版本的平均收益。
