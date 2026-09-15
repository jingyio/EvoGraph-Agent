# G-Agent 式局部规划复用 · 初始验证

日期：2026-09-10。实现协议见 [g-agent-local-composition-design-2026-09-10.md](g-agent-local-composition-design-2026-09-10.md)。本页将注入回归与真实训练严格分开。

## 已验证机制

`tests_python/test_tinyedge.py` 建立四条带不同 train workflow provenance 的注入轨迹：两条 `list -> payments`、两条 `list -> items`。矿工只从连续、非 `defer` 读取链生成闭合且 support=2 的 Persistent TinyEdge。一个不同完整 Workflow 的运行走 Composition：

- Fast 未命中；composition 角色仅调用一次 `submit_coarse_plan`，完整 Plan 请求为 0。
- 路由确定性选择两个不同 TinyEdge ID；组合器将共同的 list node 合并，生成并实际执行 `list_orders`、`get_payments`、`get_items`。
- 每个组合节点带 TinyEdge ID、来源 workflow/run，且所有参数仍为当前任务的分页和 `item.id` 绑定；没有再次调用模型选择片段。
- 组合失败、字段/类型变化和下游模型恢复继续由已有 guarded graph runtime 处理；没有 shadow rollout。

这是协议回归，不是模型性能实验。

## 正常训练尝试

临时当前代码后端 `4319` 顺序运行了五条 `train` 任务，完成后停止：

| 任务 | 运行 ID | 结果 | 路由/观察 |
|---|---|---|---|
| `finance-installments-01` | `800f792f` | 结构化评分通过，但最终模型超时 | 完整 Plan；图编译的上游列表歧义回退，未入库 |
| `finance-installments-02` | `9ef504a8` | 通过 | 保存一个含模型交接的初始图；仅一个 workflow，TinyEdge support 未达 2 |
| `finance-freight_burden-01` | `acfa3b5e` | 通过 | 图编译歧义回退，未入库 |
| `finance-freight_burden-02` | `504f58d7` | 模型超时、未提交报告 | 图不入库 |
| `finance-reconciliation-01` | `982d7e44` | 规划模型网络失败 | 未进入 Composition |

因此这轮真实训练没有 materialize Persistent TinyEdge，也没有观察到 Fast 之外的 Composition 命中、token/延迟收益或大小模型协同收益。所有失败原始运行保留在本地 artifacts；未从 validation/test 提取经验，也没有虚增图版本或制造额外 rollout。

## 本地验证

- `npm test`：67 passed。
- `npm run test:frontend`：4 passed。
- `npm run taskbank:validate`：300 任务、10,400 工具契约调用、0 模型调用。
- `npm run build`：TypeScript 与生产构建通过。

结论：三路径、Persistent TinyEdge 规范、确定性组合/绑定和 UI 可观测性已经实现。尚需在图编译稳定且模型服务可用的正常 train 流量中积累两个以上不同可执行来源，再测量真实 Composition 的质量和成本；在此之前不作性能主张。
