"""Read-only live platform pipeline. Never reseeds or falls back to fixtures."""
import asyncio
from collections import defaultdict
from decimal import Decimal
import json
from uuid import uuid4
from . import config
from .autotool import digest
from .connectors import platform_tools
from .domain import now
from .graph_store import write_private
from .runtime import create_run
from .service import RunService
from .tools import ToolContext


async def inventory(source):
    scenario = 'finance' if source == 'erpnext' else 'support'
    context = ToolContext(create_run(dict(scenario=scenario, mode='live', source=source, task='Read-only inventory')))
    tools = {tool.name: tool for tool in platform_tools(source)}
    async def listing(name, **extra):
        rows = []
        for page in range(1, 21):
            result = await tools[name].execute(dict(extra, page=page, pageSize=50), context)
            rows.extend(result['records'])
            if not result['mayHaveMore']:
                return rows
        raise ValueError('Inventory exceeds 20 pages; refusing an incomplete inventory')
    if source == 'erpnext':
        invoices = await listing('erpnext_list_invoices', status='all')
        payments = await listing('erpnext_list_payments')
        totals = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for row in invoices:
            totals[row['currency']][0] += Decimal(str(row['grand_total']))
            totals[row['currency']][1] += Decimal(str(row['outstanding_amount']))
        facts = dict(invoices=len(invoices), payments=len(payments),
                     invoiceAmountsByCurrency={key: dict(total=str(value[0]), outstanding=str(value[1])) for key, value in totals.items()})
        demo = bool(invoices and payments) and all(r['name'].startswith('RSI-INV-') for r in invoices) and all(r['name'].startswith('RSI-PAY-') for r in payments)
        stable = dict(invoices=invoices, payments=payments)
    else:
        tickets = await listing('zammad_list_tickets')
        states = await tools['zammad_list_states'].execute({}, context)
        priorities = await tools['zammad_list_priorities'].execute({}, context)
        closed_ids = {s['id'] for s in states if s['name'] == 'closed'}
        facts = dict(tickets=len(tickets), notClosed=sum(t['state_id'] not in closed_ids for t in tickets))
        demo = bool(tickets) and all(t['title'].startswith('[RSI-') for t in tickets)
        stable = dict(tickets=[{key: row.get(key) for key in ['id', 'title', 'state_id', 'owner_id', 'group_id', 'priority_id', 'first_response_escalation_at']} for row in tickets], states=states, priorities=priorities)
    return dict(source=source, provenance='project_seed_records' if demo else 'unverified_records',
                provenanceNote='当前标识符合本项目种子脚本，不能称为真实企业数据' if demo else '记录来源待核实，不能仅凭来自平台宣称真实企业数据',
                facts=facts, fingerprint=digest(stable))


def task_for(source, inspection_time):
    if source == 'erpnext':
        return (f'以 {inspection_time} 为本次巡检时刻。分页读取全部可见已提交销售发票和客户收款，读取收款详情核对 references。'
                '按币种报告发票总额、未结清余额和已分配金额，区分已有分配与本次操作。识别部分回款、重复 reference_no、未分配回款和逾期余额。'
                '金额使用平台原生单位，不按分处理。对重复流水仅提出核查，不认定新增回款或实际损失。'
                '调用 publish_report 发布有 _evidenceRef 引用的只读核查报告。不要修改平台记录或发送消息。')
    return (f'以 {inspection_time} 为本次巡检时刻。分页读取全部可见工单以及状态和优先级字典，读取未关闭工单详情和文章。'
            '报告未关闭数量、未分派数量和首响截止时间早于巡检时刻的风险；区分待核查风险与已确认 SLA 违约。'
            '不要只凭 owner_id 推断人员可用，不推断闭单是否按时。报告中引用实际读取的 _evidenceRef。'
            '调用 publish_report 保存只读服务运营简报。不要修改工单、发送消息或声称已分派/已升级。')


async def main():
    service = RunService()
    service.restore()
    batch = dict(id=str(uuid4()), startedAt=now(), pipeline='live-platform-read-only', platforms=[],
                 provenance='平台当前记录；不预设为真实企业数据', limits=dict(modelRequests=config.MAX_STEPS, toolCalls=config.MAX_TOOLS))
    path = config.ARTIFACTS / 'platform-pipelines' / (batch['id'] + '.json')
    write_private(path, batch)
    print('Pipeline ' + batch['id'], flush=True)
    for source in ['erpnext', 'zammad']:
        item = dict(source=source, runs=[])
        batch['platforms'].append(item)
        try:
            item['before'] = await inventory(source)
            print(json.dumps(item['before'], ensure_ascii=False), flush=True)
            task = task_for(source, batch['startedAt'])
            for strategy in ['react', 'graph']:
                request = dict(scenario='finance' if source == 'erpnext' else 'support', source=source, task=task,
                               mode='live', strategy=strategy, snapshot='base', negativeMotifs=False)
                run = await service.start(request)
                print(source + ' ' + strategy + ' ' + run['id'], flush=True)
                await service.tasks[run['id']]
                summary = {key: run.get(key) for key in ['id', 'status', 'metrics', 'evaluation', 'graph', 'error', 'model', 'modelSettings']}
                summary['strategy'] = strategy
                summary['reportSaved'] = bool(run.get('report'))
                item['runs'].append(summary)
                write_private(path, batch)
                print(json.dumps(summary, ensure_ascii=False), flush=True)
                if run['status'] != 'completed' or not run.get('report'):
                    raise ValueError('Platform task did not complete; no sandbox fallback or automatic retry')
                if strategy == 'react':
                    graph = await service.learn(run['id'])
                    item['learnedGraph'] = graph
                    write_private(path, batch)
            item['after'] = await inventory(source)
            item['listedStateUnchanged'] = item['before']['fingerprint'] == item['after']['fingerprint']
            item['status'] = 'completed'
        except Exception as error:
            item.update(status='failed', error=str(error)[:1000])
        write_private(path, batch)
    batch['finishedAt'] = now()
    write_private(path, batch)
    print('Saved ' + str(path), flush=True)
    if any(p['status'] != 'completed' for p in batch['platforms']):
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
