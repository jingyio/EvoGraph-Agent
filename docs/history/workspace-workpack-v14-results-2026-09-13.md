# Workpack V14 Smoke 诊断

工件：`c071e0ac-f639-440d-9733-7a46f69f9d54`。V14 修复了客服的含糊 grouped count：
客服与工单两臂均通过。但财务 `freight-contribution` 两臂均在正确键控对账后对命中订单
的 `perKey` 金额手工求和，`metrics` 校验失败并有界终止。因此 V14 为 Baseline 2/3、RSI
2/3，不能用于同质量成本结论。

V15 在同一通用对账工具中新增 comparison `matchingTotals`，将调用者显式声明的命中键、
别名和值确定性求和；模型提示要求直接使用该输出，不能手工加总。它不读取 privateValidation
或 gold，也不自动填报告，故需要新的隔离 smoke。
