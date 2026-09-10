"""Shared timestamps and platform report export; no simulated business state."""
from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent

def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def markdown(run):
    report = run.get('report')
    text = f"# {report['title'] if report else 'Agent 执行记录'}\n\n运行：{run['id']}\n\n模式：{run['request']['mode']} / {run['request'].get('strategy', 'react')}；数据源：{run['request']['source']}；状态：{run['status']}\n\n"
    if report:
        def cell(value):
            return str(value).replace('|', '\\|').replace('\n', ' ')
        text += report['summary'] + '\n\n'
        text += '\n'.join(f"- {m['label']}：{m['value']}" for m in report['metrics']) + '\n\n'
        text += '| ' + ' | '.join(map(cell, report['columns'])) + ' |\n| ' + ' | '.join('---' for _ in report['columns']) + ' |\n'
        text += '\n'.join('| ' + ' | '.join(map(cell, row)) + ' |' for row in report['rows']) + '\n\n'
        text += '\n'.join('- ' + finding for finding in report['findings']) + '\n\n'
    else:
        text += run.get('finalText', run.get('error', '尚未生成报告')) + '\n\n'
    text += '执行计量：' + json.dumps(run['metrics'], ensure_ascii=False) + '\n\n'
    if run.get('modelSettings'):
        text += '模型设置：' + json.dumps(run['modelSettings']) + '\n\n'
    if run.get('graph'):
        text += '图执行与学习（学习成本单列）：' + json.dumps(run['graph'], ensure_ascii=False) + '\n\n'
    if run.get('evaluation'):
        text += '任务结果校验：' + json.dumps(run['evaluation'], ensure_ascii=False) + '\n'
    return text
