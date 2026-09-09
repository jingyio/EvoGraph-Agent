# 财务运营与客服运营平台可用性调研

调研日期：2026-09-08；模型验证状态更新于 2026-09-09。结论区分官方文档支持、客户端协议验证和真实部署验证，不以仓库存在或 HTTP 首页可达代替业务可用性。

## 选型结论

| 平台 | 适用业务 | 官方可用能力 | 部署与接入负担判断 | 本版处理 |
|---|---|---|---|---|
| ERPNext | 应收、客户收款、发票核查、对账 | 财务业务对象、单据关联、Frappe REST API、官方 Docker 项目 | 较高：公司、科目、客户、币种、单据状态须初始化 | 财务首选；已实现分页与详情只读连接器 |
| Zammad | 工单巡检、分类、SLA、分派、服务运营 | 工单/文章/用户/状态/优先级 API，官方 Docker Compose | 中：需初始化账号、组权限、SLA 与知识内容 | 客服首选；已实现只读连接器 |
| Frappe Helpdesk | 工单、知识库、SLA、规则分派 | 官方 README 有双门户、SLA、Assignment Rules、Knowledge Base | 可与 ERPNext 共用技术栈；仍须验证 App/Framework 版本兼容 | 有价值的备选；暂未实现连接器 |

推荐当前保持 ERPNext + Zammad 两种可替换后端，以验证工具契约能够连接不同业务系统。若下一阶段更看重运维统一，可优先实测 ERPNext + Frappe Helpdesk 同一技术栈。以上接入负担为工程判断，不是部署时长实测。

## ERPNext

### 已核实

- [官方仓库](https://github.com/frappe/erpnext)：开源 ERP，包含财务、订单与库存等模块，仓库标注 GPL-3.0。
- [Frappe REST API](https://docs.frappe.io/framework/user/en/api/rest)：使用 `Authorization: token api_key:api_secret`，权限继承对应用户；DocType 自动提供 CRUD；分页为 `limit_start`、`limit_page_length`，默认列表只返回有限记录和字段。
- [Payment Reconciliation](https://docs.frappe.io/erpnext/payment-reconciliation)：将已记录付款/贷项关联到未结清发票；该动作并不产生新的银行资金流动。
- [Sales Order](https://docs.frappe.io/erpnext/sales-order)：官方描述订单、交付、发票、收款链，可作为后续拓展业务闭环的环境。
- [Frappe Docker](https://github.com/frappe/frappe_docker)：提供 `pwd.yml` 一次性演示环境以及生产 Compose 结构。官方明确演示环境不用于生产。
- [ARM64 文档](https://github.com/frappe/frappe_docker/blob/main/docs/01-getting-started/03-arm64.md)：有 Linux/Mac ARM64 设置指引，涉及镜像构建和 platform 配置；不能假定任何版本在 Apple Silicon 上直接可用。

### 当前连接器

| 工具 | 原生资源 |
|---|---|
| `erpnext_list_invoices` | 已提交 Sales Invoice，可过滤 outstanding_amount > 0 |
| `erpnext_get_invoice` | 单张 Sales Invoice 完整字段 |
| `erpnext_list_payments` | 已提交、Receive、Customer 类型的 Payment Entry |
| `erpnext_get_payment` | 单张 Payment Entry，包含可用的 references 子表 |
| `erpnext_get_customer` | Customer 主数据 |

每页最多 50 条，返回 `mayHaveMore`，不隐式声称全量。原生金额不转成“分”；`paid_amount`、`received_amount`、`unallocated_amount` 与账户币种的关系需在业务逻辑中核查。客户端附加 `_evidenceRef`，使用“资源类型:原始 ID”区分不同资源；报告必须引用实际读取的标识。列出单据不代表已经具备提交、核销或取消单据的业务能力。

正式部署验收应包含：公司/币种/科目初始化、最小权限 API 用户、一个有余额发票、部分回款和未分配收款、references 字段核对、多页列表、无权限与失败响应、快照恢复。当前尚未完成这些真实实例验收。

## Zammad

### 已核实

- [官方仓库](https://github.com/zammad/zammad)：开源客服/工单系统，仓库标注 AGPL-3.0。
- [REST API](https://docs.zammad.org/en/latest/api/intro.html)：提供 token 等认证方式及分页说明。
- [Ticket API](https://docs.zammad.org/en/latest/api/ticket/index.html)：列举工单等操作，明确 API 可见性受到用户是否为 agent 和所属组权限影响。
- [官方 Docker Compose 部署文档](https://docs.zammad.org/en/latest/install/docker-compose.html)：要求 Docker Compose 环境，至少 4 GB RAM；包含 Elasticsearch 的系统配置要求。
- [Docker Compose 仓库](https://github.com/zammad/zammad-docker-compose)：Elasticsearch 默认启用，官方说明它可选但强烈建议使用；不能在省略后假定搜索能力完全相同。

### 当前连接器

| 工具 | 原生端点 |
|---|---|
| `zammad_list_tickets` | `GET /api/v1/tickets`，page/per_page/expand |
| `zammad_get_ticket` | `GET /api/v1/tickets/{id}` |
| `zammad_get_ticket_articles` | `GET /api/v1/ticket_articles/by_ticket/{id}` |
| `zammad_list_states` | `GET /api/v1/ticket_states` |
| `zammad_list_priorities` | `GET /api/v1/ticket_priorities` |

不硬编码状态和优先级数字；保留缺失 SLA 值为 null。客户端附加包含资源类型的 `_evidenceRef`，区分同号工单、文章和字典项。当前没有外部平台写工具、文章创建、对客回复或关闭工单功能。

正式部署验收应包含：初始化测试 agent、group 与 API token，验证跨组可见性，创建不同状态和优先级的合成工单，配置 SLA 和业务日历，验证文章接口，再检查分页、超时和空数据情况。

## Frappe Helpdesk

[官方仓库](https://github.com/frappe/helpdesk) 的 README 明确列出 Agent/Customer Portal、可配置 SLA、Assignment Rules、Knowledge Base、Saved Replies，并提供 Docker 开发设置及自托管入口。其底层是 Frappe Framework，适合与 ERPNext 共用工具适配经验。

但是，通用 Frappe CRUD 不等于所有 Helpdesk 的工作流动作都已稳定暴露。本次没有验证 HD Ticket 字段、文章/分派接口或与目标 ERPNext 版本共存；不能将其视作当前代码已支持的平台。

## 当前环境实测

| 项目 | 本地 Mac | `ssh v100` |
|---|---|---|
| 操作系统/架构 | macOS / arm64 | Ubuntu 18.04 / x86_64，内核 4.15 |
| Node | v22.22.3，可运行 Agent | v16.20.1，不满足本项目 Node 22+ 要求 |
| Docker | 未安装 | 已安装 CLI 与 Compose v2.18.1 |
| Docker daemon 权限 | 不适用 | 当前 SSH 用户访问 `/var/run/docker.sock` 被拒绝 |
| 免密 sudo Docker | 不适用 | `sudo -n docker version` 返回需要密码 |
| 资源 | 已完成本地运行 | 检查时约 214 GiB 可用内存、142 GiB 家目录所在磁盘可用空间 |

本次只对 v100 进行了只读环境检查，没有安装软件、修改组权限、启动容器或改变已有服务。阻碍真实平台部署的是当前账号的 Docker 权限；资源本身足够。部署权限解决后仍需固定镜像版本并核查旧主机内核兼容性，不能据此承诺部署已经成功。

推荐使用独立的 Compose project、数据卷和仅回环监听的端口（例如 ERPNext 18080、Zammad 18081），通过 SSH 隧道访问，避免与既有服务冲突。平台自身的通知渠道先不配置，合成工单与财务单据可用于完整工具联调。

## 验证层级与结果

| 验证层级 | 当前结果 |
|---|---|
| 官方仓库、部署/API 文档核查 | 已完成 |
| 财务和客服沙箱业务规则 | 已通过自动测试与命令行完整运行 |
| ERPNext / Zammad 客户端协议 | 已用本地 HTTP 测试服务器验证鉴权、分页、编码、原生字段、错误与重定向处理 |
| 模型 function-calling 协议 | 已用本地 HTTP 测试服务器验证工具调用—观察—最终答复循环 |
| 真实 ERPNext / Zammad 部署和数据联调 | 未完成；Docker 权限受限且未提供现有实例凭据 |
| 真实外部 LLM 调用 | 2026-09-09 已用 qwen/qwen3.8-flash 完成财务、客服各一次沙箱运行；业务状态核对通过，简报仍有文字错误，详见 live-model-validation-2026-09-09.md |
| RSI 成本/质量提升 | 未测量；当前仅构建普通 ReAct 基线 |

截至本次实现，不能把协议测试或离线固定流程的结果称为平台真实联调、LLM 质量结果或 RSI 收益。
