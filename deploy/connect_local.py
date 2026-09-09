#!/usr/bin/env python3
"""Import private read-only platform credentials without changing model settings."""
import argparse
import json
import os
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['erpnext', 'zammad', 'all'], default='all')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    target = root / '.env'
    original = target.read_text() if target.exists() else (root / '.env.example').read_text()
    updates = {}
    for platform in ['erpnext', 'zammad'] if args.platform == 'all' else [args.platform]:
        credentials = json.loads((root / 'deploy' / 'runtime' / platform / '.env.credentials.json').read_text())
        keys = ['ERPNEXT_API_KEY', 'ERPNEXT_API_SECRET'] if platform == 'erpnext' else ['ZAMMAD_API_TOKEN']
        for key in keys:
            value = credentials[key]
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
                raise ValueError('Invalid credential format for ' + key)
            updates[key] = value
        updates[platform.upper() + '_BASE_URL'] = 'http://127.0.0.1:' + ('18080' if platform == 'erpnext' else '18081')
    changed = original
    for key, value in updates.items():
        pattern = r'(?m)^' + re.escape(key) + r'=.*$'
        if re.search(pattern, changed):
            changed = re.sub(pattern, lambda _: key + '=' + value, changed)
        else:
            changed = changed.rstrip() + '\n' + key + '=' + value + '\n'
    backup = root / '.env.before-platforms'
    if not backup.exists():
        fd = os.open(str(backup), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(original)
    temporary = root / '.env.platform-update'
    fd = os.open(str(temporary), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(changed)
    os.replace(str(temporary), str(target))
    os.chmod(str(target), 0o600)
    print('Configured platform variables: ' + ', '.join(sorted(updates)))
    print('Model settings preserved. Restart the local Agent service to load changes.')


if __name__ == '__main__':
    main()
