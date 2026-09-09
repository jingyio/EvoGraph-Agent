# ERPNext / Zammad 实验环境

2026-09-09 已在 `ssh v100` 部署并完成真实 API 验证。远端目录为 `/home/jingyij/rsi-business-lab`；Agent 与模型配置仍在本地项目目录。

| 平台 | 版本 | Compose project | 通过 SSH 隧道访问 |
|---|---|---|---|
| ERPNext | v16.34.2 | rsi-lab-erpnext | <http://127.0.0.1:18080> |
| Zammad | 7.1.3-0011 | rsi-lab-zammad | <http://127.0.0.1:18081> |

两个平台只在远端回环地址发布端口。当前本地隧道的控制 socket 是 `/tmp/rsi-agent-lab-v100.sock`，可以用下面的命令查看状态：

```bash
ssh -S /tmp/rsi-agent-lab-v100.sock -O check v100
```

隧道未运行时，在本地项目目录启动：

```bash
ssh -M -S /tmp/rsi-agent-lab-v100.sock -fnNT \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18080:127.0.0.1:18080 \
  -L 127.0.0.1:18081:127.0.0.1:18081 v100
```

平台页面登录信息保存在本地 `deploy/runtime/platform-access.json`，已被 Git 忽略。工作台使用独立只读用户；管理员账号用于手动检查实验平台，不交给 Agent。

## 已准备的数据

ERPNext：RSI Demo Company、人民币科目与银行账户、6 个测试客户、6 张已提交发票和 6 笔已提交收款。原始应收 ¥66,500、已分配 ¥42,000、剩余应收 ¥24,500。包含真实 references 子表中的部分分配、一笔收款分配至多张发票，以及两笔共用银行引用的待核查收款。该平台快照已包含部分正常分配，与内置沙箱“从零分配”的初始状态不同，不能直接拿两者的调用次数作优劣比较。

Zammad：6 个 RSI 工单，其中 5 个未关闭；3 个业务组；测试坐席与客户；60 分钟首响和 480 分钟解决时限的 SLA；Asia/Shanghai 日历。工单创建时间以首次 seed 的执行时刻为参照，其中两个工单首响截止时间在过去。真实平台时钟会继续前进，正式实验必须指定共同的巡检时刻或进行快照恢复，不能沿用内置沙箱的固定日期假设。

默认 Zammad 示例用户和工单仍在默认组；RSI API 用户只能读取 RSI 组，已验证访问默认工单被拒绝。Zammad 不启用 Elasticsearch 全文搜索；当前工具使用列表和 ID 详情，不依赖搜索。备份服务默认不启动，基线备份由本项目脚本手动生成。未配置对客邮件/消息渠道。

## 首次部署的可复用流程

以下命令用于新建独立实验实例。已有部署更新时不要用另一套 `.env` 覆盖远端凭据；准备脚本会保留本地已存在的密码。

1. 本地准备固定上游版本的配置：

```bash
python3 deploy/prepare.py
```

`prepare.py` 下载固定 commit 的官方 Compose 文件，设置独立项目名、回环端口和随机密码。ERPNext 管理员密码与数据库密码不同。源码 URL 和 SHA256 写入每个平台的 `source.json`。

2. 首次复制到 v100：

```bash
ssh v100 'mkdir -m 700 -p /home/jingyij/rsi-business-lab'
scp -r deploy/runtime/erpnext deploy/runtime/zammad v100:/home/jingyij/rsi-business-lab/
scp deploy/pull_images.py deploy/images.lock.json deploy/seed_erpnext.py deploy/seed_zammad.rb deploy/backup.py v100:/home/jingyij/rsi-business-lab/
```

3. 下载固定镜像并启动：

```bash
ssh v100 'python3 /home/jingyij/rsi-business-lab/pull_images.py --mirror docker.m.daocloud.io'
ssh v100 'cd /home/jingyij/rsi-business-lab/erpnext && docker compose up -d --pull never'
ssh v100 'cd /home/jingyij/rsi-business-lab/zammad && docker compose up -d --pull never'
```

本次 v100 的 Docker Hub 请求超时，使用可达镜像源下载 Docker Hub 镜像。`images.lock.json` 的六个 Docker Hub 摘要通过本地访问官方 registry 验证；Zammad 主镜像来自官方 ghcr.io，摘要也已固定。镜像源只改变下载位置，拉取仍按锁定摘要进行。镜像校验成功后才设置 Compose 所需标签，`--pull never` 避免启动时再次访问不可达源。没有修改 Docker daemon 全局镜像配置、系统内核设置或其他项目服务。

ERPNext 的 `create-site` 容器完成站点安装后再执行种子脚本；Zammad 等待 railsserver healthy。官方 Zammad init 容器可能初始化后继续驻留，不能仅依赖其是否退出判断服务可用。

4. 初始化业务记录：

```bash
ssh v100 'docker cp /home/jingyij/rsi-business-lab/seed_erpnext.py rsi-lab-erpnext-backend-1:/tmp/rsi-seed.py && docker exec -u frappe rsi-lab-erpnext-backend-1 /home/frappe/frappe-bench/env/bin/python /tmp/rsi-seed.py'
ssh v100 'docker cp /home/jingyij/rsi-business-lab/seed_zammad.rb rsi-lab-zammad-zammad-railsserver-1:/tmp/rsi-seed.rb && docker exec rsi-lab-zammad-zammad-railsserver-1 bundle exec rails runner /tmp/rsi-seed.rb'
```

脚本按 RSI 标识跳过已有记录，不负责把修改过的实验数据恢复到初始状态。ERPNext 只读角色对三个业务 DocType 授予 read/select；Zammad 用户只授予实验组的 read 权限。种子脚本从平台自身业务方法创建单据，未跳过金额或状态校验。

5. 私密复制连接信息并配置本地 Agent：

```bash
ssh v100 'docker cp rsi-lab-erpnext-backend-1:/home/frappe/frappe-bench/sites/private-rsi-connection.json /home/jingyij/rsi-business-lab/erpnext/.env.credentials.json && chmod 600 /home/jingyij/rsi-business-lab/erpnext/.env.credentials.json'
ssh v100 'docker cp rsi-lab-zammad-zammad-railsserver-1:/opt/zammad/storage/rsi-lab-credentials.json /home/jingyij/rsi-business-lab/zammad/.env.credentials.json && chmod 600 /home/jingyij/rsi-business-lab/zammad/.env.credentials.json'
scp v100:/home/jingyij/rsi-business-lab/erpnext/.env.credentials.json deploy/runtime/erpnext/.env.credentials.json
scp v100:/home/jingyij/rsi-business-lab/zammad/.env.credentials.json deploy/runtime/zammad/.env.credentials.json
python3 deploy/connect_local.py
npm run platforms
npm run verify:platforms
```

`connect_local.py` 只改平台配置，保留模型设置，并保存被忽略的 `.env.before-platforms` 备份。重启本地 Agent 后，在“真实模型 ReAct”模式下可选择 ERPNext 或 Zammad 数据源。

## API 验收与快照

`npm run verify:platforms` 现由 Python 模块 backend/verify_platforms.py 执行，仅允许指向上述本地实验隧道，校验每页 2 条的跨页读取、真实发票与收款关系、工单文章、SLA 截止时间、默认组不可见，以及只读用户同值更新返回 403。结果保存在 `artifacts/platform-deployment/verification.json`。

```bash
ssh v100 'python3 /home/jingyij/rsi-business-lab/backup.py'
```

本次快照目录：`/home/jingyij/rsi-business-lab/snapshots/20260909T054305Z`。包含 ERPNext SQL 与 sites、Zammad PostgreSQL dump 与 storage，以及文件大小和摘要清单。每个数据库采用一致性导出；两个系统之间不保证分布式事务一致性。快照内含平台密钥，仅保存在私有目录，不加入 Git。

**恢复演练尚未执行。** 正式 graph-based RSI 写任务实验前，需验证恢复流程，并冻结业务任务与评分规则。当前已接通的外部 Agent 工具全部只读；业务写入仍只在内置沙箱中实现。

## 停止与继续运行

```bash
ssh v100 'cd /home/jingyij/rsi-business-lab/erpnext && docker compose stop'
ssh v100 'cd /home/jingyij/rsi-business-lab/zammad && docker compose stop'
# 继续时分别执行 docker compose up -d --pull never。
```

这些项目名、容器和数据卷与其他工作负载隔离。日常停止不删除数据卷。
