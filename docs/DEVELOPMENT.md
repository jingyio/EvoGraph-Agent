# 开发说明

`main` 的最小机制实现可直接执行，不需要模型密钥或第三方包：

```bash
python3 -m unittest discover -s tests -v
python3 -m core.finance_demo
```

完整工程在 [`develop`](https://github.com/jingyio/EvoGraph-Agent/tree/develop) 分支，包括 FastAPI 后端、React 前端、任务资产、协议测试、历史审计和运行说明。

开发分支的基本命令：

```bash
git switch develop
npm test
npm run test:frontend
npm run build
npm run taskbank:validate
```

最近一次冻结的开发提交为 `39ca657`。该分支保留所有历史实验文档、benchmark 清单与完整源码；`main` 则保留最小机制、候选证据和面向导师的审阅入口。
