"""Frozen heterogeneous public-record task asset for trajectory RSI V3.

Task descriptors are asset-construction and offline-audit data only.  They are
never copied into a Workspace task, the matcher, the compiler, or a model
prompt.  Every task is scored from current attachments and private frozen facts.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from . import build_taskbank as sources
from .graph_store import write_private
from .workspace import WorkspaceManager

VERSION='trajectory-review-v3'
ROLE_LABELS={'finance':'财务','support':'客服','tickets':'技术工单'}

# IDs intentionally express only an offline audit order.  ``kind``/``motif``
# never travel past this module's frozen manifest and private evaluation.
TASKS={
'finance':[
 ('F01','多原因订单财务复核','reconcile','按 order_id 汇总支付、商品和运费；分别复核支付差额严格大于5分、最大分期数达到8期、缺支付和缺商品明细。', ['difference','installments','missing_payment','missing_items'],['多表关联','一对多','缺失','重叠','单位']),
 ('F02','支付方式与金额异常概览','payment','按 order_id 复核多笔支付、最大分期数达到10期、已取消但仍有支付和缺支付记录。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['多表关联','状态交叉','重叠']),
 ('F03','高金额订单支付结构复核','payment','列出支付总额较高且存在多笔支付、分期达到8期、或已取消仍支付的订单；缺支付应单列待核查。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['排序','一对多','状态交叉']),
 ('F04','确定性分段金额变化复核','reconcile','按附件订单日期的确定性前后分段比较金额复核结果，并列出差额严格大于10分、分期达到8期及资料不完整的订单。', ['difference','installments','missing_payment','missing_items'],['派生期间','多表关联','缺失']),
 ('F05','月度支付与商品金额复核','reconcile','按订单月份汇总本次附件中的支付、商品和运费，并列出差额严格大于5分、分期达到10期和资料不完整的订单。', ['difference','installments','missing_payment','missing_items'],['期间','一对多','重叠']),
 ('F06','指定支付结构内部复核','payment','针对本次订单的支付结构，列出多笔支付、最大分期数达到12期、已取消仍有支付和缺支付记录。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['筛选','状态交叉','边界']),
 ('F07','订单关联完整性待核查','reconcile','复核订单、支付和商品关联：列出缺支付、缺商品、支付差额严格大于5分和最大分期数达到8期的订单。', ['difference','installments','missing_payment','missing_items'],['缺失','一对多','重叠']),
 ('F08','金额边界与分期复核','reconcile','对附件订单执行严格边界复核：支付与商品加运费差额严格大于10分，最大分期数达到12期；缺失关联单列。', ['difference','installments','missing_payment','missing_items'],['运算符边界','单位','缺失']),
 ('F09','措辞变化的订单复核','reconcile','请找出付款和货品含运费不一致超过5分的订单、分期期数不少于8的订单，以及两侧资料不全的订单。', ['difference','installments','missing_payment','missing_items'],['重述','参数重绑定','重叠']),
 ('F10','扩展的金额与支付状态复核','payment','整理多笔支付、分期达到8期、取消后仍支付和缺支付的订单，并给出当前附件的金额概览和证据。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['覆盖扩展','金额','状态交叉']),
 ('F11','复核交接组合清单','reconcile','制作交接清单：保留支付金额差额严格大于5分、分期达到8期、缺支付和缺商品的独立原因与当前证据。', ['difference','installments','missing_payment','missing_items'],['组合','多交付','一对多']),
 ('F12','仅支付结构的局部复核','payment','仅就支付结构整理多笔支付、分期达到10期、取消仍支付和缺支付；不要把商品缺失当作支付异常。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['局部覆盖','拒绝边界']),
 ('F13','多支付与高分期交叉复核','payment','按订单汇总多种支付方式和多笔支付，列出多笔支付、最大分期数达到8期、已取消仍支付及缺支付订单。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['交叉复核','一对多','重叠']),
 ('F14','支付金额与状态优先清单','payment','生成支付优先清单，独立保留多笔支付、分期达到12期、已取消仍支付和缺支付的原因与证据。', ['multiple_payment','high_installment','canceled_paid','missing_payment'],['优先清单','状态交叉']),
 ('F15','严格差额边界复核','reconcile','只将支付总额与商品加运费差额严格大于5分的订单列为差额项，同时列出分期达到8期和关联缺失项。', ['difference','installments','missing_payment','missing_items'],['严格比较','边界','缺失']),
 ('F16','财务全范围内部简报','reconcile','完成本次附件的订单金额、分期和关联完整性简报，独立列出差额严格大于10分、分期达到10期、缺支付和缺商品。', ['difference','installments','missing_payment','missing_items'],['多交付','总览','证据']),
],
'support':[
 ('C01','投诉时效与转交复核','timing','按 complaint_id 关联本次投诉和企业响应，列出 timely 为 No、转交严格超过48小时及日期异常的投诉。', ['late','delayed_transfer','date_review'],['时间','重叠','边界']),
 ('C02','响应完整性与叙述复核','coverage','列出缺公开响应、缺企业响应、有消费者叙述但缺公开响应及缺关联记录的投诉。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['多源','文本','缺失']),
 ('C03','渠道与问题类型响应概览','coverage','按渠道和问题类型整理投诉响应完整性，列出缺公开响应、缺企业响应、叙述待跟进和缺关联记录。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['分组','文本','缺失']),
 ('C04','确定性分段投诉变化复核','timing','按附件日期的确定性前后分段复核投诉时效，列出不及时、转交严格超过72小时和日期异常的记录。', ['late','delayed_transfer','date_review'],['派生期间','时间','边界']),
 ('C05','公司集中投诉时效队列','timing','围绕同公司投诉整理内部时效队列：及时性为 No、转交严格超过96小时及日期异常应独立保留。', ['late','delayed_transfer','date_review'],['公司聚合','时间','重叠']),
 ('C06','指定期间SLA复核','timing','在本次附件范围内复核投诉SLA：列出 timely 为 No、转交严格超过72小时和日期不完整或倒置的投诉。', ['late','delayed_transfer','date_review'],['时间槽','筛选','缺失']),
 ('C07','日期与响应缺失待核查','timing','将不及时、转交严格超过48小时和日期异常的投诉独立列出；日期缺失不能被写成已按时转交。', ['late','delayed_transfer','date_review'],['缺失','时间','重叠']),
 ('C08','政策资料支持的内部跟进','coverage','根据附件中的投诉、企业响应和消费者叙述，列出缺公开响应、缺企业响应、叙述待跟进和缺关联项，并形成内部建议。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['文本证据','本地产物','缺失']),
 ('C09','时效参数重绑定复核','timing','用新的72小时口径复核转交时效，同时保留 timely 为 No 和日期异常的独立队列。', ['late','delayed_transfer','date_review'],['参数重绑定','时间边界']),
 ('C10','响应完整性覆盖扩展','coverage','除响应完整性外，请按渠道给出概览；独立列出缺公开响应、缺企业响应、叙述待跟进和缺关联。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['覆盖扩展','聚合','文本']),
 ('C11','多原因客服交接清单','timing','制作客服交接清单：timely 为 No、转交严格超过48小时和日期异常的原因可以重叠，并附当前证据。', ['late','delayed_transfer','date_review'],['组合','交接','时间']),
 ('C12','仅响应内容局部复核','coverage','仅复核公开与企业响应完整性、叙述待跟进和关联缺失；不要据此推断投诉已经解决。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['局部覆盖','拒绝边界','文本']),
 ('C13','公司产品集中度与异常交叉复核','timing','按公司和产品聚合本次投诉，列出 timely 为 No、转交严格超过72小时及日期异常的记录，并注明响应资料仍需另行核查。', ['late','delayed_transfer','date_review'],['交叉复核','公司×产品','时间']),
 ('C14','重点渠道响应证据清单','coverage','按渠道整理响应证据，独立列出缺公开响应、缺企业响应、叙述待跟进和缺关联的投诉。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['证据','分组','文本']),
 ('C15','严格时效边界复核','timing','仅当转交严格超过48小时时列入延迟项；同时列出 timely 为 No 和日期异常，恰好48小时不入选。', ['late','delayed_transfer','date_review'],['严格比较','边界','时间']),
 ('C16','客服全范围内部简报','coverage','完成当前附件的响应完整性内部简报，列出缺公开响应、缺企业响应、叙述待跟进和缺关联，并给出内部建议。', ['missing_public_response','missing_company_response','narrative_followup','missing_link'],['多交付','总览','证据']),
],
'tickets':[
 ('T01','活动与指派重点分诊','activity','按 issue_id 关联问题和活动，列出 open 且评论达到3条、其中未指派，以及缺活动关联的事项。', ['focus','unassigned_focus','missing_activity'],['状态','活动','缺失']),
 ('T02','排期与指派复核','readiness','对 open 问题列出无里程碑、未指派、带 bug 标签和缺活动关联的事项。', ['no_milestone','unassigned','bug_label','missing_activity'],['多原因','重叠','状态']),
 ('T03','标签与活动优先队列','activity','整理 open 且评论达到5条的问题，独立列出其中未指派和活动关联缺失的事项。', ['focus','unassigned_focus','missing_activity'],['筛选','活动','优先级']),
 ('T04','确定性分段工单变化复核','readiness','按附件更新时间的确定性前后分段复核 open 工单，列出无里程碑、未指派、bug 标签和缺活动关联。', ['no_milestone','unassigned','bug_label','missing_activity'],['派生期间','状态','变化']),
 ('T05','长期活动问题分诊','activity','围绕本次附件中开放且评论达到8条的问题，列出未指派和缺活动关联项，形成内部优先队列。', ['focus','unassigned_focus','missing_activity'],['时间','活动','优先队列']),
 ('T06','状态与活动冲突待核查','activity','复核开放问题中评论达到5条的事项，独立列出未指派和缺活动关联，不能根据评论数断定故障严重性。', ['focus','unassigned_focus','missing_activity'],['状态冲突','活动','边界']),
 ('T07','负责人和排期完整性','readiness','对 open 问题分别列出无里程碑、未指派、bug 标签和缺活动关联；原因可重叠。', ['no_milestone','unassigned','bug_label','missing_activity'],['缺失','重叠','状态']),
 ('T08','标题标签证据清单','readiness','按当前标题、标签和更新时间整理研发交接清单，独立列出无里程碑、未指派、bug 标签和缺活动关联。', ['no_milestone','unassigned','bug_label','missing_activity'],['文本','标签','证据']),
 ('T09','评论阈值重新绑定','activity','使用评论达到5条的新口径分诊 open 问题，并单列未指派和缺活动关联。', ['focus','unassigned_focus','missing_activity'],['参数重绑定','活动','状态']),
 ('T10','活动分诊覆盖扩展','activity','除重点活动队列外，形成内部交接建议；列出 open 且评论达到3条、其中未指派和缺活动关联的事项。', ['focus','unassigned_focus','missing_activity'],['覆盖扩展','多交付','活动']),
 ('T11','活动标签排期组合交接','readiness','制作研发交接清单，独立保留无里程碑、未指派、bug 标签和缺活动关联的 open 问题及链接。', ['no_milestone','unassigned','bug_label','missing_activity'],['组合','交接','标签']),
 ('T12','仅导出变化局部复核','readiness','仅复核 open 工单的里程碑、指派、bug 标签和活动关联完整性；不要修改任何工单。', ['no_milestone','unassigned','bug_label','missing_activity'],['局部覆盖','拒绝边界']),
 ('T13','负责人标签里程碑活动联合风险复核','readiness','联合复核 open 问题的负责人、标签、里程碑和活动关联，独立列出无里程碑、未指派、bug 标签和缺活动项。', ['no_milestone','unassigned','bug_label','missing_activity'],['联合风险','多条件','重叠']),
 ('T14','未指派高活动优先清单','activity','列出 open 且评论达到8条的问题，重点标明其中未指派及缺活动关联的事项和当前链接。', ['focus','unassigned_focus','missing_activity'],['排序','活动','链接']),
 ('T15','状态与标签边界复核','readiness','仅对 open 问题列出无里程碑、未指派、标签包含 bug 和缺活动关联的事项；已关闭问题不入选。', ['no_milestone','unassigned','bug_label','missing_activity'],['边界','状态','标签']),
 ('T16','技术工单全范围简报','readiness','完成当前附件的排期、指派、标签和活动完整性简报，独立列出无里程碑、未指派、bug 标签和缺活动事项。', ['no_milestone','unassigned','bug_label','missing_activity'],['总览','多交付','证据']),
],
}

PRECHECK={'finance':{'F01','F05','F10','F11'}, 'support':{'C01','C04','C10','C11'}, 'tickets':{'T01','T04','T10','T11'}}


def _hours(start,end):
    try:return (datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds()/3600
    except (AttributeError,TypeError,ValueError):return None


def _suffix(request, metrics, groups):
    return request.strip()+ '\n请提交以下整数指标：'+ '、'.join(metrics)+'。原因分组必须使用：'+ '、'.join(groups)+'；每组提供 reason、condition、count、selectedIds 和当前证据。空组也必须如实提交。'


def task_plan():
    rows=[]
    for role, items in TASKS.items():
        for pos,(key,title,kind,request,groups,features) in enumerate(items,1):
            rows.append(dict(id=key,scenario=role,title=title,kind=kind,position=pos,split='train',precheck=key in PRECHECK[role],auditFeatures=features))
        # Independent records, held out from all learning and opportunity accounting.
        for split, positions in [('validation',(2,12)),('test',(4,15))]:
            for ordinal, pos in enumerate(positions,1):
                key,title,kind,request,groups,features=items[pos-1]
                rows.append(dict(id=f'{key}-{split[0].upper()}{ordinal}',scenario=role,title=title+'（'+split+'）',kind=kind,position=pos,split=split,precheck=False,auditFeatures=features))
    return rows


def _finance(records,kind,position):
    tables={'orders':[{'order_id':r['id'],'status':r['status'],'purchased_at':r['purchased_at'],'purchased_month':(r['purchased_at'] or '')[:7]} for r in records],
            'payments':[dict(order_id=r['id'],**p) for r in records for p in r['payments']],
            'items':[{'order_id':r['id'],'sequence':p['sequence'],'price_cents':p['price_cents'],'freight_cents':p['freight_cents']} for r in records for p in r['items']]}
    paid={r['id']:sum(p['amount_cents'] for p in r['payments']) for r in records};line={r['id']:sum(p['price_cents']+p['freight_cents'] for p in r['items']) for r in records}
    terms={r['id']:max([p['installments'] for p in r['payments']],default=None) for r in records}
    delta=10 if position in {4,8,16} else 5; threshold=12 if position in {6,8,14} else 10 if position in {2,5,12,16} else 8
    if kind=='reconcile':
        groups={'difference':[r['id'] for r in records if r['payments'] and r['items'] and abs(paid[r['id']]-line[r['id']])>delta],
                'installments':[r['id'] for r in records if terms[r['id']] is not None and terms[r['id']]>=threshold],
                'missing_payment':[r['id'] for r in records if not r['payments']], 'missing_items':[r['id'] for r in records if not r['items']]}
        metrics={'order_count':len(records),'paid_cents':sum(paid.values()),'line_cents':sum(line.values()),**{f'{k}_count':len(v) for k,v in groups.items()}}
    else:
        groups={'multiple_payment':[r['id'] for r in records if len(r['payments'])>=2],
                'high_installment':[r['id'] for r in records if terms[r['id']] is not None and terms[r['id']]>=threshold],
                'canceled_paid':[r['id'] for r in records if r['status']=='canceled' and r['payments']], 'missing_payment':[r['id'] for r in records if not r['payments']]}
        metrics={'order_count':len(records),'payment_record_count':sum(len(r['payments']) for r in records),'paid_cents':sum(paid.values()),'period_count':len({(r['purchased_at'] or '')[:7] for r in records}),**{f'{k}_count':len(v) for k,v in groups.items()}}
    return tables,metrics,groups


def _support(records,kind,position):
    tables={'complaints':[{'complaint_id':r['id'],'company':r['company'],'product':r['product'],'issue':r['issue'],'timely':r['timely'],'submitted_via':r['submitted_via']} for r in records],
            'responses':[{'complaint_id':r['id'],'company_public_response':r['company_public_response'],'company_response':r['company_response'],'date_received':r['date_received'],'date_sent_to_company':r['date_sent_to_company']} for r in records],
            'narratives':[{'complaint_id':r['id'],'narrative_excerpt':r['narrative'][:1200],'excerpt_truncated':len(r['narrative'])>1200} for r in records]}
    if kind=='timing':
        limit=96 if position==5 else 72 if position in {4,6,9,13} else 48;hours={r['id']:_hours(r['date_received'],r['date_sent_to_company']) for r in records}
        groups={'late':[r['id'] for r in records if r['timely']=='No'], 'delayed_transfer':[r['id'] for r in records if hours[r['id']] is not None and hours[r['id']]>limit], 'date_review':[r['id'] for r in records if hours[r['id']] is None or hours[r['id']]<0]}
        metrics={'complaint_count':len(records),'company_count':len({r['company'] for r in records}),**{f'{k}_count':len(v) for k,v in groups.items()}}
    else:
        groups={'missing_public_response':[r['id'] for r in records if not (r['company_public_response'] or '').strip()], 'missing_company_response':[r['id'] for r in records if not (r['company_response'] or '').strip()], 'narrative_followup':[r['id'] for r in records if r['narrative'].strip() and not (r['company_public_response'] or '').strip()], 'missing_link':[]}
        metrics={'complaint_count':len(records),'channel_count':len({r['submitted_via'] for r in records}),**{f'{k}_count':len(v) for k,v in groups.items()}}
    return tables,metrics,groups


def _tickets(records,kind,position):
    tables={'issues':[{'issue_id':r['id'],'title':r['title'],'state':r['state'],'milestone':(r['milestone'] or {}).get('title') or '','url':r['url']} for r in records],
            'activity':[{'issue_id':r['id'],'comments':r['comments'],'assignee_count':r['assignee_count'],'updated_at':r['updated_at'],'labels':', '.join(r['labels'])} for r in records]}
    if kind=='activity':
        threshold=8 if position in {5,14} else 5 if position in {3,6,9} else 3;focus=[r['id'] for r in records if r['state']=='open' and r['comments']>=threshold]
        groups={'focus':focus,'unassigned_focus':[r['id'] for r in records if r['id'] in focus and r['assignee_count']==0],'missing_activity':[]}
        metrics={'issue_count':len(records),'open_count':sum(r['state']=='open' for r in records),'closed_count':sum(r['state']=='closed' for r in records),'open_comment_total':sum(r['comments'] for r in records if r['state']=='open'),**{f'{k}_count':len(v) for k,v in groups.items()}}
    else:
        groups={'no_milestone':[r['id'] for r in records if r['state']=='open' and not r['milestone']], 'unassigned':[r['id'] for r in records if r['state']=='open' and r['assignee_count']==0], 'bug_label':[r['id'] for r in records if r['state']=='open' and any(x.lower()=='bug' for x in r['labels'])], 'missing_activity':[]}
        metrics={'issue_count':len(records),'open_count':sum(r['state']=='open' for r in records),**{f'{k}_count':len(v) for k,v in groups.items()}}
    return tables,metrics,groups


def material(spec, records):
    role=spec['scenario']
    if role=='finance': tables,metrics,groups=_finance(records,spec['kind'],spec['position'])
    elif role=='support':tables,metrics,groups=_support(records,spec['kind'],spec['position'])
    else:tables,metrics,groups=_tickets(records,spec['kind'],spec['position'])
    template=next(row for row in TASKS[role] if row[0]==spec['id'].split('-')[0])
    request=_suffix('请根据本次附件生成内部业务简报，范围只限本次资料。'+template[3]+' 原因可重叠；缺失资料不得当作已完成或零值。给出业务ID、当前证据、汇总指标和内部建议。只生成本地报告，不执行外部操作。',list(metrics),list(groups))
    return tables,request,{'metrics':metrics,'groups':{k:sorted(v) for k,v in groups.items()},'selectedIds':sorted({x for values in groups.values() for x in values})}


def build(root):
    root=Path(root);out=root/'artifacts'/VERSION
    if (out/'manifest.json').exists():
        manifest=json.loads((out/'manifest.json').read_text());write_private(root/'benchmarks'/'history'/f'{VERSION}.json',manifest);return manifest
    original=sources.fetch;sources.fetch=lambda url,path:path.read_bytes()
    manifest={'version':VERSION,'taskDesignVersion':'heterogeneous-operations-v3','taskDesign':'48 project-authored heterogeneous business requests over disjoint public records; audit labels are offline only','splitPolicy':'train only learning; validation/test frozen and unrun','protocol':{'trainPairs':48,'validationPairs':6,'testPairs':6,'precheckPairs':12,'organization':'three scenarios × sixteen heterogeneous train requests; twelve fixed precheck pairs'},'tasks':[],'sources':{}}
    try:
        loaded={}
        for role,loader in [('finance',sources.olist),('support',sources.complaints),('tickets',sources.issues)]:loaded[role],manifest['sources'][role]=loader()
        offsets=Counter()
        for spec in task_plan():
            role,split=spec['scenario'],spec['split'];pool=sorted([r for r in loaded[role] if sources.partition(r,role)==split],key=lambda r:hashlib.sha256((VERSION+role+split+r['id']).encode()).hexdigest())
            size=12 if role=='finance' else 10;start=offsets[(role,split)]*size;records=pool[start:start+size];offsets[(role,split)]+=1
            if len(records)!=size:raise ValueError(f'insufficient disjoint source records: {role}/{split}')
            tables,request,expected=material(spec,records);directory=out/spec['id'];write_private(directory/'inputs.json',tables);write_private(directory/'request.txt',request);write_private(directory/'private.json',expected)
            features={'primaryRecords':size,'rowsByTable':{k:len(v) for k,v in tables.items()},'tables':len(tables),'deliveryGroups':len(expected['groups']),'textCharacters':len(json.dumps(tables,ensure_ascii=False)),'unit':'BRL cents' if role=='finance' else 'records','association':'one-to-many' if role=='finance' else 'one-to-one','missingCells':sum(v in (None,'') for rows in tables.values() for row in rows for v in row.values()),'auditFeatures':spec['auditFeatures']}
            manifest['tasks'].append({**spec,'group':spec['kind'],'groupLabel':spec['title'],'recordIds':[r['id'] for r in records],'features':features,'requiredMetricKeys':list(expected['metrics']),'requiredGroupNames':list(expected['groups']),'requestHash':hashlib.sha256(request.encode()).hexdigest(),'inputHash':hashlib.sha256((directory/'inputs.json').read_bytes()).hexdigest()})
        audit=opportunity_audit(manifest)
        matrix={}
        for row in audit:
            for capability in row['auditFeatures']:
                matrix.setdefault(row['scenario'],{}).setdefault(capability,[]).append(row['taskId'])
        write_private(out/'manifest.json',manifest);write_private(root/'benchmarks'/'history'/f'{VERSION}.json',manifest)
        write_private(root/'benchmarks'/'history'/f'{VERSION}-opportunity-audit.json',{'version':VERSION,'generatedFromManifest':True,'offlineOnly':True,'rows':audit,'capabilityRecurrenceMatrix':matrix,'limitations':['机会来自冻结任务的公开能力标签，不是运行命中、质量、效率或进化结论。','标签绝不传给Agent、匹配器、编译器或模型。']})
        return manifest
    finally:sources.fetch=original


def install(manager:WorkspaceManager,root,spec):
    directory=Path(root)/'artifacts'/VERSION/spec['id'];workspace=manager.create(spec['scenario'],label=spec['title'],provenance='public_historical_trajectory_v3')
    manager.add_source(workspace['id'],'inputs.json',(directory/'inputs.json').read_bytes(),provenance={'source':ROLE_LABELS[spec['scenario']]+'公开历史资料；任务由项目编写'})
    task,questions=manager.create_task(workspace['id'],(directory/'request.txt').read_text(),title=spec['title'],split=spec['split'])
    if questions:raise ValueError(questions)
    internal=manager.tasks[task['id']];required=sorted(f'workspace:{workspace["id"]}:{row["rowId"]}' for table in manager.workspace(workspace['id'])['tables'].values() for row in table['rows'])
    internal['publicScopeEvidenceIds']=required;internal['privateValidation']=dict(json.loads((directory/'private.json').read_text()),requiredEvidenceIds=required)
    internal['deliveryContract']={'requiredTableSlots':list(internal['tableBindings']),'requiredMetricKeys':list(spec['requiredMetricKeys']),'requiredGroupNames':list(spec['requiredGroupNames']),'evidenceScope':'current attachment rows; no outside records'}
    manager._persist(manager.workspace(workspace['id']));return workspace,manager.public_task(task['id'])


def opportunity_audit(manifest):
    """Offline recurrence audit. No runtime component imports or reads this."""
    rows=[]
    for role in ROLE_LABELS:
        seen={};role_rows=[t for t in manifest['tasks'] if t['scenario']==role and t['split']=='train']
        for task in role_rows:
            abilities=task['features']['auditFeatures'];prior=sorted({source for ability in abilities for source in seen.get(ability,[])})
            kind='cold' if not prior else 'full_or_partial_opportunity'
            rows.append({'taskId':task['id'],'scenario':role,'offlineAuditOnly':True,'priorSources':prior,'opportunity':kind,'auditFeatures':abilities})
            for ability in abilities:seen.setdefault(ability,[]).append(task['id'])
    return rows


if __name__=='__main__':
    from .config import ROOT
    result=build(ROOT);print(json.dumps({'version':result['version'],'tasks':len(result['tasks']),'splits':dict(Counter(t['split'] for t in result['tasks']))},ensure_ascii=False))
