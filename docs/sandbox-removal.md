# 旧沙箱清理与交接

日期：2026-09-10。用户在文档整理过程中明确要求删除旧沙箱，因此本轮不再只做文档修改。

删除范围：合成业务 JSON 与 presets、两份沙箱工具规格、sandbox_tools 与领域业务运算、固定流程 provider、专用 evolution/reliability/negative_motif、对应页面/共享类型/CLI命令/API。默认首页转为真实执行演示；旧 snapshot、evolutions、reliability、negative-motifs API 返回404，sandbox/fixture执行请求被拒绝。

本地原始文件按 metadata 精确清理：source=sandbox 的旧 UUID 运行目录与旧图，以及沙箱专用进化/稳定性/负motif目录，共46项入口。没有删除当前 taskbank-runs、online-graphs、paired-evaluations、llm-judgements 或真实平台运行记录。旧运行代码可从Git历史查看；本地未入Git的已删沙箱运行文件不能假定仍可访问。

保留并修整真实平台路径：RunService/runtime/GraphStore、ERPNext/Zammad连接器、只读API和pipeline。平台运行创建空观察上下文，不再加载合成业务状态。平台图的独立验证成本与当前任务库在线进化仍需区分。旧沙箱专用负motif删除不影响 online_evolution 中的失败子图修订。

验证：61个Python测试、4个回放测试、构建和300条任务库契约校验通过。沙箱专用测试已删除，共用模型/图/协议测试使用小型注入工具；新增回归确认旧接口拒绝、平台运行与导出仍可执行。未为本轮清理调用真实LLM。

平台检查发现本地SSH隧道失效，远端v100容器仍运行。本轮重新建立18080/18081转发；实际连接检查结果见状态快照，不能把文档当作永久健康状态。

项目记忆入口为 README、AGENTS、docs/ARCHITECTURE.md、DESIGN_DECISIONS.md、TODO.md、EXPERIMENT_STATUS.md、EXECUTION_HANDOFF.md 和 .codex/state.md。
