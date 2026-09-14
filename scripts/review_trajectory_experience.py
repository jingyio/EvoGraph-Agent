"""Audit an executed trajectory before explicitly installing read-only product reuse.

Does not run an Agent or change the experiment's learned versions. The installed
copy is marked as a protocol review, never as independent prose/quality review.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID

from backend import config, trajectory
from backend.autotool import digest
from backend.graph_store import write_private
from backend.workspace import WorkspaceManager


def audit(experiment_id,graph_id):
    UUID(experiment_id);UUID(graph_id)
    root=config.ROOT/'artifacts/trajectory-experiments'/experiment_id
    item=json.loads((root/'experiment.json').read_text())
    if item['status']=='running':raise ValueError('先等当前实验终态，避免审核在途版本')
    library=json.loads((root/'rsi/experience.json').read_text())
    version=next(v for v in library['versions'] if v['id']==graph_id)
    if version.get('protocol')!=trajectory.PROTOCOL:raise ValueError('经验协议不属于当前runtime')
    if version.get('supersededBy'):raise ValueError('旧版本已被后继替代')
    source=json.loads((root/'rsi/runs'/(version['sourceRunId']+'.json')).read_text())
    if source['status']!='completed' or source['evaluation']['status']!='passed':raise ValueError('来源任务未通过')
    if version['sourceTraceDigest']!=digest(source['toolTrace']):raise ValueError('来源收据摘要不一致')
    manager=WorkspaceManager(root);manager.restore()
    task=manager.task(source['taskId']);tools=manager.tools(task['id'])
    proposal=trajectory.induce(source,task,tools)
    if not proposal or proposal['nodes']!=version['nodes']:raise ValueError('来源轨迹不能重建当前结构')
    result=deepcopy(version)
    result['reviewed']=True
    result['reviewRecord']={'kind':'execution-agent-protocol-review','experimentId':experiment_id,
                            'sourceRunId':source['id'],'sourceTraceDigest':version['sourceTraceDigest'],
                            'limitations':'结构/来源/当前槽协议审核；报告正文非独立人工质量评定；每次仍需语义兼容性判断。'}
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',required=True);parser.add_argument('--graph',required=True)
    parser.add_argument('--install',action='store_true',help='explicitly install reviewed copy in product read-only library')
    args=parser.parse_args();version=audit(args.experiment,args.graph)
    if args.install:
        path=config.ROOT/'artifacts/workspace-runtime/experience.json'
        library=json.loads(path.read_text()) if path.exists() else {'schemaVersion':3,'versions':[],'workflows':[],'tinyEdges':[]}
        library['versions']=[v for v in library.get('versions',[]) if v['id']!=version['id']]+[version]
        write_private(path,library)
    print(json.dumps({'graphId':version['id'],'G':version['generation'],'M':version['matchVersion'],
                      'installed':args.install,'review':version['reviewRecord']},ensure_ascii=False))

if __name__=='__main__':main()
