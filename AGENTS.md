# 项目协作约定

- 用户要求使用 Git 管理本项目。仓库根目录为 `rsi-agent-lab`。
- 修改前检查 Git 状态，保留用户已有修改；按可审查的功能单元创建本地提交。
- 提交前检查 diff，并执行与改动相关的验证。主要命令：`npm test`、`npm run build`。
- 不提交真实 `.env`、密钥、`node_modules`、`dist` 或 `artifacts` 中的运行记录；保留 `.env.example`。
- 业务平台和真实模型的接入状态必须如实记录；离线固定流程不能作为真实 LLM 或 RSI 实验结果。
