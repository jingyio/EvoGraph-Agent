import argparse
import asyncio
import json
import uvicorn
from . import config

def main():
    parser = argparse.ArgumentParser(description='RSI Agent Lab')
    parser.add_argument('command', nargs='?', default='serve', choices=['serve', 'platforms'])
    parser.add_argument('--reload', action='store_true')
    args = parser.parse_args()
    if args.command == 'serve':
        uvicorn.run('backend.app:app', host='127.0.0.1', port=config.PORT, reload=args.reload,
                    reload_dirs=[str(config.ROOT / 'backend')] if args.reload else None)
    else:
        from .platform_check import check_platforms
        print(json.dumps(asyncio.run(check_platforms()), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
