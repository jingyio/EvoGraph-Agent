#!/usr/bin/env python3
"""Run one frozen attribution stage and print its saved summary."""
import argparse
import asyncio
import json
from pathlib import Path

from backend.attribution_experiment import AttributionExperiment


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('smoke', 'probe', 'repair_probe', 'formal'))
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    experiment = AttributionExperiment(Path(args.root))
    experiment.restore()
    started = await experiment.start(args.mode)
    experiment_id = started['id']
    await experiment.tasks[experiment_id]
    saved = experiment.get(experiment_id)
    summary = saved['summary']
    print(json.dumps({
        'id': experiment_id,
        'mode': saved['mode'],
        'status': saved['status'],
        'assetVersion': saved['assetVersion'],
        'fingerprint': saved['fingerprint']['digest'],
        'predecessorId': saved.get('predecessorId'),
        'summary': {
            'arms': summary['arms'],
            'protocolComplete': summary['protocolComplete'],
            'qualityGate': summary['qualityGate'],
            'costConclusionAllowed': summary['costConclusionAllowed'],
            'netTokenSaving': summary['netTokenSaving'],
            'netLatencySaving': summary['netLatencySaving'],
            'actualGraphUse': summary['actualGraphUse'],
            'learning': {
                'createdTaskIds': [point['taskId'] for point in summary['learning']['created']],
                'revisionTaskIds': [point['taskId'] for point in summary['learning']['revisions']],
                'laterUse': summary['learning']['laterUse'],
                'revisionWithLaterUse': summary['learning']['revisionWithLaterUse'],
            },
            'points': [{
                'taskId': point['taskId'],
                'noLearningStatus': point['noLearning']['status'],
                'noLearningEvaluation': (point['noLearning'].get('evaluation') or {}).get('status'),
                'onlineRsiStatus': point['onlineRsi']['status'],
                'onlineRsiEvaluation': (point['onlineRsi'].get('evaluation') or {}).get('status'),
                'tokenSaving': point['tokenSaving'],
                'latencySaving': point['latencySaving'],
                'usedVersionId': point['usedVersionId'],
                'generatedVersionIds': point['generatedVersionIds'],
            } for point in summary['points']],
        },
    }, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
