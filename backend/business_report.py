"""Common report layout using submitted facts and observed evidence, never gold answers."""
from html import escape
import json

ROLE_META = {
    'finance': ('财务运营助手', '订单异常与支付风险简报'),
    'support': ('客服运营分析师', '投诉渠道与响应健康简报'),
    'tickets': ('技术研发管理助手', 'Issue 健康与待办简报'),
}


def evidence_rows(run):
    rows = {}
    for event in run.get('events', []):
        if event['type'] != 'observation' or not (event.get('detail') or {}).get('ok'):
            continue
        value = event['detail'].get('result')
        candidates = value.get('records', [value]) if isinstance(value, dict) else value if isinstance(value, list) else []
        for row in candidates:
            if isinstance(row, dict) and row.get('_evidenceRef'):
                rows.setdefault(row['_evidenceRef'], {}).update(row)
    return rows


def render_report(run, task):
    text = lambda value: escape(str(value))
    pretty = lambda value: text(json.dumps(value, ensure_ascii=False, indent=2))
    submission = run.get('submission') or {}
    metrics = submission.get('metrics') or {}
    evidence = evidence_rows(run)
    selected = set(submission.get('selectedIds') or [])
    passed = run.get('evaluation', {}).get('status') == 'passed'
    role, deliverable = ROLE_META.get(task.get('scenario'), ('企业运营分析数字员工', '业务分析简报'))
    cards = ''.join(f'<article><small>{text(key)}</small><strong>{text(value) if not isinstance(value, dict) else text(sum(value.values()))}</strong>'
                    + (f'<pre>{pretty(value)}</pre>' if isinstance(value, dict) else '') + '</article>' for key, value in metrics.items())
    records = ''.join('<tr><td>' + text(ref) + '</td><td>' + ('入选' if row.get('id') in selected else '证据记录') + '</td><td>'
                      + '<details><summary>' + text(row.get('title') or row.get('product') or row.get('status') or '查看读取字段') + '</summary><pre>'
                      + pretty(row) + '</pre></details></td></tr>' for ref, row in sorted(evidence.items()))
    review_required = run.get('evaluation', {}).get('status') == 'user_review_required'
    quality = ('结构化事实与证据校验通过' if passed else
               '已保存，等待用户复核（当前用户资料没有私有参考答案）' if review_required else
               '未通过结构化校验 / 尚未完成')
    issues = run.get('evaluation', {}).get('issues') or []
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{text(task['title'])} · 业务报告</title><style>
body{{font:14px/1.8 system-ui,sans-serif;color:#26394a;background:#f4f7f9;margin:0}}main{{max-width:980px;margin:36px auto;background:white;padding:40px;border:1px solid #dce4e9;border-radius:12px}}header{{border-bottom:3px solid #27876c;padding-bottom:20px}}h1{{font-size:28px;margin:10px 0}}h2{{font-size:18px;margin-top:28px}}small,.meta{{color:#738592}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:15px}}article{{border:1px solid #dae6df;border-radius:8px;padding:16px;background:#f5faf7}}strong{{font-size:26px;display:block}}pre{{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #e0e7ec;vertical-align:top;overflow-wrap:anywhere}}.summary{{white-space:pre-wrap;background:#f5f8fb;padding:20px;border-radius:8px}}.status{{color:{'#237657' if passed else '#b36043'}}}footer{{border-top:1px solid #dce4e9;padding-top:16px;margin-top:24px;font-size:12px;color:#6d8291}}@media print{{body{{background:white}}main{{margin:0;border:0;padding:0}}details{{break-inside:avoid}}}}@media(max-width:600px){{main{{margin:0;padding:20px}}}}
</style><main><header><small>{text(role)} · {text(deliverable)} / 历史记录分析</small><h1>{text(task['title'])}</h1><p class="meta">{text(task['id'])} · {task['recordCount']} 条任务范围记录 · {text(task['asOf'])} · 执行状态 {text(run.get('status', 'unknown'))}</p><p class="status">{quality}</p></header>
<h2>任务要求</h2><p>{text(task['task'])}</p>
<h2>提交的业务指标</h2><div class="cards">{cards or '<p>尚未提交指标</p>'}</div><p class="meta">金额字段以任务约定单位为准；财务 *_cents 单位为 BRL 分。分组指标的大号数字是组内数值之和。</p>
<h2>模型工作结论</h2><p class="meta">以下文字来自模型，结构化评分不等于文字事实与表述已审核。</p><div class="summary">{text(submission.get('summary') or '尚未生成报告')}</div>
<h2>筛选清单</h2><pre>{pretty(submission.get('selectedIds') or [])}</pre>
<h2>逐条工具证据 · {len(evidence)} 条</h2><table><thead><tr><th>证据引用</th><th>筛选状态</th><th>本次实际读取内容</th></tr></thead><tbody>{records}</tbody></table>
<h2>质量复核</h2><p>结构化校验问题：{text(', '.join(issues) or '无')}</p><pre>{pretty(run.get('manualReview') or {'status': 'pending', 'note': '文字事实一致性、需求覆盖与可读性待人工复核'})}</pre>
<footer>来源：{text(task.get('sourceUrl', '当前工作区资料'))}<br>只展示本次工具实际读取的字段，不载入参考答案。记录 ID：{text(run['id'])}。本报告使用所有 Agent 共用的模板。</footer></main></html>'''
