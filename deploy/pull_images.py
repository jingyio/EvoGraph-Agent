#!/usr/bin/env python3
"""Fetch digest-locked images; optionally use a Docker Hub mirror without daemon changes."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mirror', default='', help='Docker Hub mirror hostname, e.g. docker.m.daocloud.io')
    parser.add_argument('--lock', type=Path, default=Path(__file__).resolve().with_name('images.lock.json'))
    parser.add_argument('--log-dir', type=Path, default=Path(__file__).resolve().parent / 'runtime' / 'pull-logs')
    parser.add_argument('--jobs', type=int, default=3, choices=range(1, 7))
    args = parser.parse_args()
    if args.mirror and not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]+)?', args.mirror):
        parser.error('--mirror must be a hostname, not a URL or credential')
    images = json.loads(args.lock.read_text())
    args.log_dir.mkdir(parents=True, exist_ok=True)

    def pull(image):
        repo, tag, digest = image['repository'], image['tag'], image['digest']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise ValueError('Invalid locked image digest')
        target = repo + ':' + tag
        check = subprocess.run(['docker', 'image', 'inspect', target, '--format', '{{json .RepoDigests}}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if check.returncode == 0 and any(value.endswith('@' + digest) for value in (json.loads(check.stdout) or [])):
            return {'image': target, 'status': 'verified_cached', 'digest': digest}
        source = (args.mirror + '/' if args.mirror and not repo.startswith('ghcr.io/') else '') + repo + '@' + digest
        path = args.log_dir / (repo.replace('/', '-') + '-' + tag + '.log')
        print('Fetching ' + target + ' by locked digest', flush=True)
        with path.open('w') as log:
            process = subprocess.run(['docker', 'pull', source], stdout=log, stderr=subprocess.STDOUT, timeout=900)
        if process.returncode:
            return {'image': target, 'status': 'failed', 'log': str(path), 'detail': path.read_text()[-1200:]}
        subprocess.run(['docker', 'tag', source, target], check=True)
        return {'image': target, 'status': 'ready', 'digest': digest}

    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(pull, image) for image in images]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except Exception as error:
                result = {'status': 'failed', 'detail': str(error)}
            print(json.dumps(result), flush=True)
            failures += result['status'] == 'failed'
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
