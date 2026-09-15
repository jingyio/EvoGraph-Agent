# Benchmark 资产

顶层仅保留当前任务库、当前发布清单和下一阶段候选：

- `manifest.json` / `tasks.jsonl`：300 个公开历史数据任务及来源清单。
- `finance-rsi-attribution-v5-12.json`：当前财务 12 任务候选发布。
- `cross-domain-rsi-attribution-v1-48.json`：跨场景后续候选。
- `trajectory-review-v3-r3.json` 与机会审计：当前 P0.5 候选资产。
- `showcase-tasks-v1.json`：演示任务。
- `workpacks-v1.json`：历史工作包入口仍使用的兼容资产。

被后续版本替代的冻结清单保存在 [`history/`](history/)。这些文件仍供 release 深链和回归测试读取，不参与当前指标选择。
