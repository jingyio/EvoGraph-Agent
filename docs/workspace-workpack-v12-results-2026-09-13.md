# Workpack V12 运行结果与边界

日期：2026-09-13。原始工件保存在本机
`artifacts/workpack-experiments/`，不入 Git。

## 版本缘由

V11 正式流 `365db551-2457-4464-917a-7604fae3949c` 的 Baseline 48/48，
RSI 47/48，token 为 2,288,906→1,503,742（表面 -34.303%）。
RSI 的 `finance-freight-contribution-02` 在 Fast 路径重复调用同一确定性
`workspace_aggregate_rows`，耗尽模型请求预算且未提交报告。因此 V11 只能作为
负向诊断，不能用于同质量成本结论。

V12 新增双方共享的重复确定性计算保护：模型拥有的 `compute` 工具若已在当前
工作区以同一规范化参数成功调用，拒绝重复调用并保留 `compute_guard` 事件。
它不拦截读取、artifact/publish 或运行时恢复调用；目的仅是避免相同计算不能带来
新观察时继续消耗模型预算。该共享修复建立了新的 runtime fingerprint，不能复用
V11 的严格对照。

## 阶段证据

| 阶段 | 工件 ID | 结果 | 边界 |
|---|---|---|---|
| Smoke | `2413c09a-93e6-4f32-9bc4-110ed9c439b3` | 两臂 3/3 通过；Baseline/RSI 201,454/74,589 token | 当前 fingerprint 的三场景质量前置；双方各实际拒绝 1 次重复确定性计算。 |
| Precheck | `587d7c50-044b-45b8-be3d-63663e8f0eee` | 两臂 12/12 通过；429,009→325,277 token（-24.179%）；RSI 6 个初始 Workflow、4 次 Fast | 同质量的小样本预检通过，但未达到 30% 目标；Composition 为 0。 |
| Full train | `f8acd9e2-b387-4e2c-b56d-dc1720a9de2c` | Baseline 42/48、RSI 46/48；1,813,753→1,078,947 token（表面 -40.513%） | **质量门槛失败，且末尾模型网络故障；不得主张相同质量 token 节省。** |

Full train 的 RSI 形成 12 个初始 Workflow、后续实际 Fast 复用 36 次、
Fallback 12 次、Composition 0。经验维护错误为 0；本地 RSI 开销为 lookup
42.494ms、compile 31.748ms、binding 1.472ms、maintenance 248.302ms、persist
390.172ms。`compositionModelWallMs=24,670.673` 为模型等待，单列而非本地编译。

## Full train 失败与可靠性

所有 48 对均保留。Baseline 的 `finance-freight-contribution-01` 在 180,012ms
总时限后失败；`finance-freight-contribution-03` 和
`finance-link-completeness-04` 均在两次失败报告后有界终止。随后
`tickets-blocker-summary-04` 遇到模型请求超时；最后两个任务
`tickets-activity-followup-04`、`tickets-export-comparison-04` 两臂均遭遇模型
网络连接失败。后两项是系统性服务异常，按协议不应被当作业务/RSI机制优劣。

Baseline 共有 11 次失败报告、9 个运行发生报告恢复、2 个运行重复失败；RSI
共有 1 次失败报告、1 个运行恢复、0 个重复失败。两臂各有一次重复确定性计算
被 guard 拒绝，维护错误均为 0。由于两臂没有都通过冻结范围，以上差异只能用于
定位恢复与服务可靠性风险，不构成公平的质量或经济性比较。

## 结论与后续

- V12 验证了共享 guard 的回归和预检健康，但未证明完整流的同质量收益。
- Fast 复用确实改变了后续 36 个 RSI 任务的执行；这不是 G1/G2 结构修订，也没有
  Composition 证据。
- 不对 V12 做 Judge：Agent runtime 已出现质量不完整与系统性网络失败，Judge 不会
  修复或澄清该事实。
- 若重启 Workpack 全量实验，先单独诊断并稳定模型服务/连接，再建立新的 runtime
  或服务版本和新的 smoke；不得从 V12 中挑选成功子集重算收益。
