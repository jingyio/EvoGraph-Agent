# 项目协作约定

- 用户要求使用 Git 管理本项目。仓库根目录为 `rsi-agent-lab`。
- 修改前检查 Git 状态，保留用户已有修改；按可审查的功能单元创建本地提交。
- 后端使用 Python/FastAPI，前端使用 React/TypeScript。TS 后端基线保存在 Git 提交 `e63b138`。
- 提交前检查 diff，并执行与改动相关的验证。主要命令：`npm test`（pytest）、`npm run build`，真实平台验收使用 `npm run verify:platforms`。
- 不提交真实 `.env`、密钥、`node_modules`、`dist` 或 `artifacts` 中的运行记录；保留 `.env.example`。
- 业务平台和真实模型的接入状态必须如实记录；离线固定流程不能作为真实 LLM 或 RSI 实验结果。
- 模型 HTTP 调用统一放在 `backend/model_client.py`，业务模块只依赖注入接口；按用户要求关闭思考模式（`enable_thinking: false`，OpenRouter 同时发送 `reasoning.enabled: false`）。
- 确定性任务校验失败时，不得把“执行结束”当作任务成功，也不得自动晋升为新经验。自定义任务未选择完整校验目标时，只检查状态约束并明确标注范围。
