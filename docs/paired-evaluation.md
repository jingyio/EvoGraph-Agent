# 冻结成对评测与业务成果

入口 `http://127.0.0.1:5173/#evaluation`。目标与证据边界见 [mentor-goals.md](mentor-goals.md)。

## 实验协议

- Strong ReAct 与 Graph RSI 共用 `backend/agent_prompts.py` 的通用观察复用、防重复、批量读取和发布前检查指令。普通 ReAct 保留供历史演示。
- 从所选 validation/test 划分，每场景每类型取按 ID 排序的首个任务，共 30 个任务。选择在结果产生前完成。每轮可重复 1–3 次，所有重复都保留。
- 两边使用相同执行模型、工具实现和评分器。Strong ReAct 不调用 Plan；RSI 没有图时正常调用 Plan，命中时跳过 Plan。
- 启动时固定图快照、任务与数据集摘要、工具契约哈希、源码哈希、模型名、预算与调度限制；不在评测过程中学习或修改经验。没有适用图就记录冷启动，不把少数已有图外推到整个任务库。
- 两对任务并发，一对内的两个 Agent 均执行一次；交替 A/B 提交顺序。共享调度资源，结果不是隔离单任务 latency 基准，也不代表高并发吞吐测量。
- API 在评测期间阻止额外任务库任务提交。取消后停止子任务并保留已有计量。服务中断后恢复已保存子任务结果，不自动重跑。

所有尝试计入总 token、模型/工具调用、错误与延迟。每成功任务 token = 全部尝试 token / 成功任务数，因此不会藏掉失败成本。用量不完整则关闭精确 token 降幅和每成功任务成本结论。双方通过子集另列，不能替代主统计。

## 业务结果

`GET /api/taskbank/runs/<id>/report` 返回所有策略共用模板的 HTML 报告：任务要求、提交指标、筛选清单、模型结论、实际工具证据、结构化评分及人工复核状态。未读取的数据和 gold 不进入报告；不执行模型返回的 HTML。浏览器可打印为 PDF。

`POST /api/taskbank/runs/<id>/review` 接受人工评分：事实一致性、需求覆盖、可读性各 0/1/2，以及依据说明。默认未评；系统不自行填入“人工通过”，也不把人工文字评分覆盖到原始结构化评分。

## API 与持久化

```text
POST /api/evaluations
{"split":"validation","repeats":1}

GET /api/evaluations
GET /api/evaluations/<id>
POST /api/evaluations/<id>/cancel
```

结果保存在 `artifacts/paired-evaluations/<id>.json`，每个子运行仍进入 `artifacts/taskbank-runs/`，可以从评测页直接打开准确配对的轨迹回放。后续新评测还会把源码快照保存在 `artifacts/paired-evaluations/sources/<id>.json`；首次开发中验收仅记录启动时源码哈希和 Git 基线，没有这一快照文件。

`historicalSetupTokens` 只统计冻结图直接来源、可追溯的历史任务；不代表完整研发或全部图谱建立成本，不能把它包装为完整摊销结果。美元成本尚未配置输入/输出单价，保留实际 token 计量。

这轮实验用于验证与发现瓶颈，测试集尚未使用。单轮每任务一次不足以证明长期可靠性；多代图演化仍必须由真实训练轨迹产生，不能根据验证集结果直接生成经验。
