"""Explicit release selection and read-only evidence projection. Never learns/runs.

A missing/mismatched artifact fails closed; no fallback to another experiment.
Every drilldown rechecks membership in the pinned release and pair.
"""
from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path
from urllib.parse import quote
from .trajectory_experiment import summary
from .workspace import WorkspaceManager


def selection_csv(submission):
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(['原因', '条件', '业务ID', '组数量', '证据'])
    groups = submission.get('groups') or [{'name': '清单', 'condition': '', 'selectedIds': submission.get('selectedIds', []), 'count': len(submission.get('selectedIds', [])), 'evidenceIds': submission.get('evidenceIds', [])}]
    def safe(value):
        text = str(value)
        return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text
    for group in groups:
        for key in group.get('selectedIds') or ['']:
            writer.writerow([safe(v) for v in [group.get('reason') or group['name'], group.get('condition', ''), key, group.get('count', 0), ' | '.join(group.get('evidenceIds', []))]])
    return '\ufeff' + stream.getvalue()


class ReleaseEvidence:
    def __init__(self, root):
        self.root = Path(root)

    def registry(self):
        data = json.loads((self.root / 'releases/manifest.json').read_text())
        ids = [r['releaseId'] for r in data['releases']]
        if len(ids) != len(set(ids)) or data['currentReleaseId'] not in ids:
            raise ValueError('发布清单身份无效')
        for row in data['releases']:
            if row['status'] not in ('candidate', 'formal', 'historical'):
                raise ValueError('发布状态无效')
        return data

    def manifest(self, key=None):
        data = self.registry()
        key = key or data['currentReleaseId']
        row = next((r for r in data['releases'] if r['releaseId'] == key), None)
        if row is None:
            raise KeyError('发布版本不存在')
        return deepcopy(row)

    def experiment(self, key):
        release = self.manifest(key)
        if release['source'] != 'trajectory':
            raise ValueError('该历史发布使用独立历史审计入口')
        directory = self.root / 'artifacts/trajectory-experiments' / release['experimentId']
        item = json.loads((directory / 'experiment.json').read_text())
        if (item['id'] != release['experimentId'] or item['assetVersion'] != release['assetVersion'] or
                'sha256:' + item['fingerprint']['digest'] != release['runtimeRevision'] or item['protocol'] != release['protocol']):
            raise ValueError('保存工件与发布清单不一致；拒绝替换数据来源')
        return release, item, directory

    def _pair(self, key, pair_id):
        release, item, directory = self.experiment(key)
        pair = next((p for p in item['pairs'] if p['spec']['id'] == pair_id), None)
        if pair is None:
            raise KeyError('任务不属于该发布')
        return release, item, directory, pair

    def run(self, key, pair_id, arm):
        release, _, directory, pair = self._pair(key, pair_id)
        if arm not in ('baseline', 'rsi') or not pair.get(arm):
            raise KeyError('该侧没有保存运行')
        stored = pair[arm]
        run = json.loads((directory / arm / 'runs' / (stored['id'] + '.json')).read_text())
        if run['id'] != stored['id'] or run['taskId'] != pair['taskId']:
            raise ValueError('运行身份与发布任务不一致')
        return {'releaseId': release['releaseId'], 'experimentId': release['experimentId'], 'pairId': pair_id,
                'arm': arm, 'run': run}

    def _workspace(self, directory, pair):
        manager = WorkspaceManager(directory)
        manager.restore()  # In-memory only; never persists or creates a workspace.
        return manager, manager.task(pair['taskId'])

    def pair(self, key, pair_id):
        release, _, directory, pair = self._pair(key, pair_id)
        manager, task = self._workspace(directory, pair)
        workspace = manager.public_workspace(task['workspaceId'])
        base = f'/api/releases/{quote(key)}/pairs/{quote(pair_id)}'
        return {'releaseId': key, 'experimentId': release['experimentId'], 'pairId': pair_id,
                'task': manager.public_task(task['id']),
                'inputs': [{'id': s['id'], 'name': s['name'], 'sizeBytes': s['sizeBytes'], 'provenance': s.get('provenance'),
                            'download': base + '/inputs/' + s['id']} for s in workspace['sources']],
                'tables': workspace['tables'],
                'runs': {arm: self.run(key, pair_id, arm)['run'] for arm in ('baseline', 'rsi') if pair.get(arm)}}

    def input_file(self, key, pair_id, source_id):
        _, _, directory, pair = self._pair(key, pair_id)
        manager, task = self._workspace(directory, pair)
        return manager.source_path(task['workspaceId'], source_id), manager.source_name(task['workspaceId'], source_id)

    def report(self, key, pair_id, arm):
        from .business_report import render_report
        _, _, directory, pair = self._pair(key, pair_id)
        manager, task = self._workspace(directory, pair)
        run = self.run(key, pair_id, arm)['run']
        # Render only the saved submission; never fills/re-executes an artifact.
        return render_report(run, task)

    def evidence(self, key):
        release, item, directory = self.experiment(key)
        # Use membership-checked saved runs for every metric, report and curve.
        item = deepcopy(item)
        pairs = []
        for pair in item['pairs']:
            pair_id = pair['spec']['id']
            for arm in ('baseline', 'rsi'):
                if pair.get(arm):
                    pair[arm] = self.run(key, pair_id, arm)['run']
            pairs.append({'pairId': pair_id, 'title': pair['spec']['title'], 'scenario': pair['spec']['scenario'],
                          'position': pair['spec']['position'], 'status': pair['status'], 'features': pair['spec']['features'],
                          'detail': f'/api/releases/{quote(key)}/pairs/{quote(pair_id)}',
                          'runs': {a: {k: pair[a].get(k) for k in ['id', 'status', 'metrics', 'evaluation']}
                                   for a in ('baseline', 'rsi') if pair.get(a)}})
        metrics = summary(item)
        revisions = []
        # Extract revisions from the source run receipt, not today's shared graph library.
        sources = {}
        for i, pair in enumerate(item['pairs']):
            run = pair.get('rsi') or {}
            compilation = (run.get('evolution') or {}).get('trajectoryCompilation') or {}
            sources[run.get('id')] = (i, pair, compilation)
        for source_id, (index, pair, compilation) in sources.items():
            if not compilation:
                continue
            for graph_id in (pair['rsi'].get('evolution') or {}).get('generatedVersionIds', []):
                patches = compilation.get('patches') or []
                g_change = any(p.get('before') and p.get('after') and p['before'] != p['after'] for p in patches)
                m_patches = compilation.get('matchPatches') or []
                m_change = any(p.get('before') and p.get('after') and p['before'] != p['after'] for p in m_patches)
                if not g_change and not m_change:
                    continue  # G0/M0 creation is not a revision.
                uses = []
                for later in item['pairs'][index + 1:]:
                    r = later.get('rsi') or {}
                    e = r.get('evolution') or {}
                    if e.get('usedVersionId') == graph_id and any(t.get('executor') == 'graph' and t.get('ok') for t in r.get('toolTrace', [])):
                        uses.append({'pairId': later['spec']['id'], 'runId': r['id'], 'matchVersion': e.get('matchVersion'), 'evaluation': r.get('evaluation')})
                revisions.append({'graphId': graph_id, 'sourceRunId': source_id, 'sourcePairId': pair['spec']['id'],
                                  'graphChanged': g_change, 'matchingChanged': m_change, 'subsequentUses': uses,
                                  'graphDiff': patches, 'matchingDiff': m_patches})
        return {'release': release, 'experimentStatus': item['status'], 'summary': metrics, 'pairs': pairs,
                'plannedPairs': len(item['manifest']), 'revisions': revisions,
                'evolutionEvidence': {'graph': any(r['graphChanged'] and r['subsequentUses'] for r in revisions),
                                      'matching': any(r['matchingChanged'] and r['subsequentUses'] for r in revisions)}}

    def archive(self):
        registry = self.registry()
        rows = []
        for source, folder, page, asset in [('trajectory', 'trajectory-experiments', 'trajectory', 'trajectory-review-v1'),
                                           ('workpack', 'workpack-experiments', 'experiments', 'workpacks-v1')]:
            for path in sorted((self.root / 'artifacts' / folder).glob('*/experiment.json')):
                item = json.loads(path.read_text())
                if source == 'trajectory':
                    revision = 'sha256:' + item.get('fingerprint', {}).get('digest', 'unrecorded')
                else:
                    fp = item.get('protocol', {}).get('runtimeFingerprint') or {}
                    revision = 'sha256:' + str(fp.get('executionDigest') or fp.get('digest') or '未记录')
                declared = next((r for r in registry['releases'] if r['experimentId'] == item['id']), None)
                rows.append({'releaseId': declared['releaseId'] if declared else None,
                             'displayName': declared['displayName'] if declared else item.get('protocol', {}).get('id') or item.get('mode', source),
                             'status': declared['status'] if declared else 'historical', 'experimentStatus': item['status'],
                             'experimentId': item['id'], 'runtimeRevision': revision, 'assetVersion': item.get('assetVersion', asset),
                             'protocol': {k: v for k, v in item.get('protocol', {}).items() if k in ('id', 'runtimeProtocol', 'limits', 'model', 'planner', 'purpose')}, 'createdAt': item.get('createdAt'),
                             'href': '#archive?page=' + page + '&experiment=' + quote(item['id'])})
        for release in registry['releases']:
            if release['source'] == 'online-e2e':
                rows.append(dict(release, href='#archive?page=compare&release=' + release['releaseId']))
        return {'items': rows, 'legacyRoutes': {route: self.manifest(key) for route, key in registry.get('legacyRoutes', {}).items()}, 'legacyRelease': next(r for r in registry['releases'] if r['source'] == 'online-e2e')}
