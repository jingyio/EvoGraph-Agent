"""Versioned public-source request assets. Private truth is evaluation only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from . import build_taskbank as sources
from .graph_store import write_private
from .workspace import WorkspaceManager

VERSION='trajectory-review-v1'
ROLE_LABELS={'finance':'财务','support':'客服','tickets':'技术工单'}


def material(role, records, position):
    extension = position in (3,4,7,8)
    if role=='finance':
        delta,terms=[(5,8),(10,12),(5,8),(10,8),(5,12),(10,8),(10,12),(5,8)][(position-1)%8]
        tables={'orders':[{'order_id':r['id'],'status':r['status'],'purchased_at':r['purchased_at']} for r in records],
                'payments':[dict(order_id=r['id'],**p) for r in records for p in r['payments']],
                'items':[{'order_id':r['id'],'sequence':p['sequence'],'price_cents':p['price_cents'],'freight_cents':p['freight_cents']} for r in records for p in r['items']]}
        request=f'''请根据这份订单、支付和商品明细做一份财务复核简报，范围只限本次附件。
按 order_id 汇总每个订单的支付金额、商品金额及运费。一个订单可以有多笔支付、多条商品明细，不要把它们当作重复行直接删除。
请分别列出：支付总额与商品金额加运费总额相差严格大于{delta}分的订单；最大分期数达到{terms}期（>={terms}）的订单。两类可以重叠，不要合并后丢掉原因。
缺支付记录或缺商品明细的订单单独列为待核查，不能当成金额为零已完成对账。
给出附件内订单数、支付总额、商品加运费总额、各类复核订单数，附订单ID及证据；金额展示为BRL并注明原始字段为分。
最后给出内部复核建议。即使某类没有入选订单，也请明确写0并说明筛选条件。只分析和生成报告，不执行退款或改账。'''
        if position%2==0:
            request+=' 请先呈现金额总览，再分原因列清单；每一份支付和商品明细均需保留在其订单汇总中。'
        groups={'difference':[], 'installments':[], 'missing_payment':[], 'missing_items':[]}
        paid_total=line_total=0
        for r in records:
            paid=sum(p['amount_cents'] for p in r['payments']); line=sum(p['price_cents']+p['freight_cents'] for p in r['items'])
            paid_total+=paid;line_total+=line
            if r['payments'] and r['items'] and abs(paid-line)>delta:groups['difference'].append(r['id'])
            if r['payments'] and max(p['installments'] for p in r['payments'])>=terms:groups['installments'].append(r['id'])
            if not r['payments']:groups['missing_payment'].append(r['id'])
            if not r['items']:groups['missing_items'].append(r['id'])
        metrics={'order_count':len(records),'paid_cents':paid_total,'line_cents':line_total,**{k+'_count':len(v) for k,v in groups.items()}}
        if extension:
            request+=' 另外单独列出 status 等于 canceled 且确有支付记录的订单组 canceled_paid，统计 canceled_paid_count；它与其他原因独立。'
            groups['canceled_paid']=[r['id'] for r in records if r['status']=='canceled' and r['payments']]
            metrics['canceled_paid_count']=len(groups['canceled_paid'])
    elif role=='support':
        tables={'complaints':[{'complaint_id':r['id'],'company':r['company'],'product':r['product'],'timely':r['timely'],'submitted_via':r['submitted_via']} for r in records],
                'responses':[{'complaint_id':r['id'],'company_public_response':r['company_public_response'],'company_response':r['company_response'],'date_received':r['date_received']} for r in records],
                'narratives':[{'complaint_id':r['id'],'narrative_excerpt':r['narrative'][:1200],'excerpt_truncated':len(r['narrative'])>1200} for r in records]}
        request='仅根据本次CFPB公开投诉附件，按 complaint_id 关联三表，做内部响应复核简报。timely 等于 No 单列 late；company_public_response 为 null 或空字符串或仅空白的单列 missing_response。这是不同原因，允许重叠；不能把缺少公开响应当成没有联系客户。给出投诉数 complaint_count、两组数量及各组ID和证据。引用当前叙述片段时标明消费者陈述，excerpt_truncated=true表示仅提供摘录。给内部跟进建议，不向外发送。即使空组也明确0和筛选条件。'
        groups={'late':[r['id'] for r in records if r['timely']=='No'], 'missing_response':[r['id'] for r in records if not (r['company_public_response'] or '').strip()]}
        metrics={'complaint_count':len(records),**{k+'_count':len(v) for k,v in groups.items()}}
        if extension:
            request+=' 另列 narrative_excerpt 非空的组 has_narrative 及 has_narrative_count，保留原两组。'
            groups['has_narrative']=[r['id'] for r in records if r['narrative'].strip()];metrics['has_narrative_count']=len(groups['has_narrative'])
    else:
        limit=[5,8,5,8,5,8,8,5][(position-1)%8]
        tables={'issues':[{'issue_id':r['id'],'title':r['title'],'state':r['state'],'milestone':(r['milestone'] or {}).get('title') or '', 'url':r['url']} for r in records],
                'activity':[{'issue_id':r['id'],'comments':r['comments'],'assignee_count':r['assignee_count'],'updated_at':r['updated_at'],'labels':', '.join(r['labels'])} for r in records]}
        request=f'请根据本次Zammad GitHub Issues附件做内部工程交接简报，范围只限附件，按 issue_id 关联活动与问题。state 等于 open 且 assignee_count 等于0的组 unassigned；state 等于 open 且 comments 大于等于{limit}的组 discussion。原因独立、允许重叠。给出问题数 issue_count、各组数量、ID、来源链接和证据，说明这些是公开软件问题而非内部工单。展示标签与更新日期帮助人工分诊；没有匹配的组也明确0和条件。给内部建议，不改指派、不关单。'
        groups={'unassigned':[r['id'] for r in records if r['state']=='open' and r['assignee_count']==0],
                'discussion':[r['id'] for r in records if r['state']=='open' and r['comments']>=limit]}
        metrics={'issue_count':len(records),**{k+'_count':len(v) for k,v in groups.items()}}
        if extension:
            request+=' 再加 state=open 且 milestone 为空的 no_milestone 组和 no_milestone_count，便于人工确认排期。'
            groups['no_milestone']=[r['id'] for r in records if r['state']=='open' and not r['milestone']];metrics['no_milestone_count']=len(groups['no_milestone'])
    # Explicit public output keys specify shape/meaning, never instance truth.
    request+=' 输出 metrics 精确包含以下键：'+ '、'.join(metrics)+'。groups 使用以下name，逐组给 reason、condition、count、selectedIds、evidenceIds：'+ '、'.join(groups)+'。selectedIds 是各组去重并集，所有ID用字符串。'
    expected={'metrics':metrics,'groups':{k:sorted(v) for k,v in groups.items()},'selectedIds':sorted({v for values in groups.values() for v in values})}
    return tables,request,expected


def build(root):
    root=Path(root);out=root/'artifacts'/VERSION
    if (out/'manifest.json').exists():
        return json.loads((out/'manifest.json').read_text())
    original=sources.fetch
    sources.fetch=lambda url,path:path.read_bytes()
    manifest={'version':VERSION,'taskDesign':'project-authored requests, public historical records; no injected business/tool failures',
              'splitPolicy':'source partition, train only learning; validation/test remain unrun', 'tasks':[], 'sources':{}}
    try:
        for role,loader in [('finance',sources.olist),('support',sources.complaints),('tickets',sources.issues)]:
            rows,source=loader();manifest['sources'][role]=source
            for split,count in [('train',8),('validation',1),('test',1)]:
                pool=[r for r in rows if sources.partition(r,role)==split]
                pool.sort(key=lambda r:hashlib.sha256((VERSION+role+r['id']).encode()).hexdigest())
                size=12 if role=='finance' else 10
                if len(pool)<count*size:raise ValueError('insufficient disjoint source records')
                for i in range(count):
                    position=i+1;records=pool[i*size:(i+1)*size]
                    tables,request,expected=material(role,records,position)
                    key=f'{role}-{split}-{position:02d}'
                    directory=out/key
                    write_private(directory/'inputs.json',tables)
                    write_private(directory/'request.txt',request)
                    write_private(directory/'private.json',expected)
                    features={'primaryRecords':size,'rowsByTable':{k:len(v) for k,v in tables.items()},'tables':len(tables),
                              'deliveryGroups':len(expected['groups']),'textCharacters':len(json.dumps(tables,ensure_ascii=False)),
                              'unit':'BRL cents' if role=='finance' else 'records','association':'one-to-many' if role=='finance' else 'one-to-one',
                              'missingCells':sum(v in (None,'') for rows_ in tables.values() for row in rows_ for v in row.values())}
                    manifest['tasks'].append({'id':key,'scenario':role,'split':split,'position':position,'group':role+'-review',
                        'title':ROLE_LABELS[role]+'多原因复核 '+str(position),'recordIds':[r['id'] for r in records],
                        'features':features,'requestHash':hashlib.sha256(request.encode()).hexdigest(),
                        'inputHash':hashlib.sha256((directory/'inputs.json').read_bytes()).hexdigest()})
        write_private(out/'manifest.json',manifest)
        return manifest
    finally:sources.fetch=original


def install(manager:WorkspaceManager, root, spec):
    directory=Path(root)/'artifacts'/VERSION/spec['id']
    w=manager.create(spec['scenario'],label=spec['title'],provenance='public_historical_trajectory_v1')
    manager.add_source(w['id'],'inputs.json',(directory/'inputs.json').read_bytes(),provenance={'source':ROLE_LABELS[spec['scenario']]+'公开历史资料；任务由项目编写'})
    task,questions=manager.create_task(w['id'],(directory/'request.txt').read_text(),title=spec['title'],split=spec['split'])
    if questions:raise ValueError(questions)
    internal=manager.tasks[task['id']]
    required=sorted(f'workspace:{w["id"]}:{row["rowId"]}' for table in manager.workspace(w['id'])['tables'].values() for row in table['rows'])
    internal['publicScopeEvidenceIds']=required
    internal['privateValidation']=dict(json.loads((directory/'private.json').read_text()),requiredEvidenceIds=required)
    internal['deliveryContract']={'requiredTableSlots':list(internal['tableBindings']), 'evidenceScope':'current attachment rows; no outside records'}
    manager._persist(manager.workspace(w['id']))
    return w,manager.public_task(task['id'])


if __name__=='__main__':
    from .config import ROOT
    m=build(ROOT)
    print(json.dumps({'version':m['version'],'tasks':len(m['tasks']),'train':sum(t['split']=='train' for t in m['tasks'])}))
