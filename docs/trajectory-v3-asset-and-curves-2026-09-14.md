# P0.5 V3任务资产与当前证据曲线

日期：2026-09-14。本阶段只构建任务资产、发布读取和展示，不运行Agent或Judge。

## 统一任务资产

`trajectory-review-v2` 固定60项：48 train、6 validation、6 test。train按三场景、每场景
两个业务问题契约、每组八个不同记录实例组织。每场景主问题前三个实例组成固定9对预检；
只有同runtime预检的两臂质量、usage和维护门槛全部通过，控制器才允许48项full。

六个公开问题为：财务订单金额与分期复核、财务支付结构与期间复核、投诉时效与转交复核、
投诉响应完整性复核、问题活动分诊、问题排期与指派复核。题面包含业务口径、缺失处理、
独立原因、证据与禁止外部写入，不包含工具名、调用顺序或私有答案。实验组标签只用于
控制器统计，不进入Workspace task的family/template或匹配输入。

受版本控制的 `benchmarks/trajectory-review-v2.json` 保存公开任务身份、记录ID、问题/输入
哈希和难度特征；完整输入与私有评分留在 ignored artifacts。三个场景内部使用的源记录
分别为240、200、200条，任务间业务ID不重叠。

根目录 `test/` 的六个问题由同一 `request_for` 定义生成。Excel仍使用此前按固定哈希选取的
Olist、CFPB和Zammad GitHub Issues公开记录。新增字段只来自原缓存：客服公开响应与叙述；
`purchased_month` 是 `purchased_at` 的前七个字符，叙述摘录是源文本前1200字符。来源审计在
`test/.rsi/provenance.json` 区分源字段和确定性派生字段。六份XLSX均通过真实上传解析器逐值
比较和临时任务创建，没有模型调用。

## 发布与曲线

当前发布改为 `trajectory-p05-v3-candidate`，状态candidate，实验ID为明确的`not-started`。
它只读取并校验公开资产清单，返回计划48、运行0和空证据。旧
`96c69be0-fc62-494a-b05d-2267d0925c03` 改为historical，原4对运行和失败不改写。

当前证据已恢复四条保存工件曲线：单任务token节省率、单任务串行latency节省率、累计净
token节省率和累计净串行latency节省率，并保留两臂绝对token、请求、延迟和成功率曲线。
失败pair只要usage完整就进入累计分母；任一侧usage不完整时单任务token为缺口，之后累计
token也保持未知。G/M标记只来自同release的真实修订来源，初次G0/M0不标为修订。

本阶段没有效率、效果、可靠性或递归进化的新结论。新候选运行前空曲线是正确状态，不能
用V17、V4或旧V2结果补齐。
