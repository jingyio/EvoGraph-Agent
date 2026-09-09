import argparse
import asyncio
import json
import uvicorn
from . import config
from .domain import PRESETS
from .service import RunService


def main():
    parser = argparse.ArgumentParser(description='Python RSI Agent Lab')
    parser.add_argument('command', nargs='?', default='serve', choices=['serve', 'demo', 'platforms'])
    parser.add_argument('--scenario', choices=['finance', 'support'], default='finance')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--strategy', choices=['react', 'graph'], default='react')
    parser.add_argument('--snapshot', choices=['base', 'changed', 'exception'], default='base')
    parser.add_argument('--reload', action='store_true')
    args = parser.parse_args()
    if args.command == 'serve':
        uvicorn.run('backend.app:app', host='127.0.0.1', port=config.PORT, reload=args.reload, reload_dirs=[str(config.ROOT / 'backend')] if args.reload else None)
    elif args.command == 'platforms':
        from .platform_check import check_platforms
        print(json.dumps(asyncio.run(check_platforms()), ensure_ascii=False, indent=2))
    else:
        async def demo():
            service = RunService()
            service.restore()
            run = await service.start({'scenario': args.scenario, 'mode': 'live' if args.live else 'fixture', 'source': 'sandbox', 'task': PRESETS[args.scenario], 'strategy': args.strategy, 'snapshot': args.snapshot})
            await service.tasks[run['id']]
            print(json.dumps({key: run.get(key) for key in ['id', 'status', 'metrics', 'evaluation', 'graph', 'error']}, ensure_ascii=False, indent=2))
            if run['status'] != 'completed' or run.get('evaluation', {}).get('status') == 'failed':
                raise SystemExit(1)
        asyncio.run(demo())


if __name__ == '__main__':
    main()
