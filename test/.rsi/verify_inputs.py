"""Check each shipped workbook using the actual upload parser, without LLMs."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.workspace import WorkspaceManager, _parse_source
from backend.trajectory_assets import request_for

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'test'
specs = json.loads((DATA / '.rsi/data.json').read_text())
results = []
with TemporaryDirectory() as temporary:
    manager = WorkspaceManager(Path(temporary))
    for spec in specs:
        path = DATA / spec['path']
        role = {'财务': 'finance', '客服': 'support', '技术工单': 'tickets'}[path.parent.name]
        parsed = dict(_parse_source(path.name, path.read_bytes()))
        expected = spec['tables']
        assert parsed == expected, f'Upload parser changed source data: {spec["path"]}'
        workspace = manager.create(role, label='input-verification')
        manager.add_source(workspace['id'], path.name, path.read_bytes())
        question = path.parent / ('问题-小幅变化.txt' if '扩展版' in path.name else '问题.txt')
        groups = {'finance': ('reconciliation', 'payment_structure'),
                  'support': ('transfer_timing', 'response_coverage'),
                  'tickets': ('activity_triage', 'release_readiness')}
        expected_question = request_for(role, groups[role]['扩展版' in path.name], 1) + '\n'
        assert question.read_text() == expected_question, f'Manual question drifted from shared contract: {question}'
        task, clarifications = manager.create_task(workspace['id'], question.read_text())
        assert task is not None and not clarifications, (spec['path'], clarifications)
        results.append(dict(file=spec['path'], sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            tables={name: len(rows) for name, rows in parsed.items()},
                            exactSourceValues=True, uploadAndTaskCreation=True))
        print(spec['path'], 'PASS', results[-1]['tables'])
(DATA / '.rsi/verification.json').write_text(json.dumps(dict(modelCalls=0, checks=results), ensure_ascii=False, indent=2))
