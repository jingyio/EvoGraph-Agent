#!/usr/bin/env python3
"""Run one frozen attribution stage and print its saved summary."""
import argparse
import asyncio
import json
from pathlib import Path

from backend.attribution_experiment import AttributionExperiment


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('smoke', 'probe', 'formal'))
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    experiment = AttributionExperiment(Path(args.root))
    experiment.restore()
    started = await experiment.start(args.mode)
    experiment_id = started['id']
    await experiment.tasks[experiment_id]
    saved = experiment.get(experiment_id)
    print(json.dumps({
        'id': experiment_id,
        'mode': saved['mode'],
        'status': saved['status'],
        'assetVersion': saved['assetVersion'],
        'fingerprint': saved['fingerprint']['digest'],
        'predecessorId': saved.get('predecessorId'),
        'summary': saved['summary'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
