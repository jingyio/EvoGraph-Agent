#!/usr/bin/env python3
"""Save private baseline dumps for the two isolated RSI Compose projects.

No services are stopped and no data is restored or deleted. Database dumps are
transactionally consistent individually; this is not a cross-platform transaction.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'rsi-business-lab')
    args = parser.parse_args()
    for platform in ['erpnext', 'zammad']:
        if not (args.root / platform / 'source.json').exists():
            raise RuntimeError('Expected prepared RSI deployment: ' + platform)
    target = args.root / 'snapshots' / datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    target.mkdir(parents=True, mode=0o700)
    query = 'import json;print(json.load(open("/home/frappe/frappe-bench/sites/frontend/site_config.json"))["db_name"])'
    database = subprocess.check_output(['docker', 'exec', 'rsi-lab-erpnext-backend-1', '/home/frappe/frappe-bench/env/bin/python', '-c', query], universal_newlines=True).strip()
    if not database or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for char in database):
        raise RuntimeError('Unexpected site database name')
    commands = [
        ('erpnext.sql', ['docker', 'exec', 'rsi-lab-erpnext-db-1', 'sh', '-c', 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump -u root --single-transaction --routines --triggers --events --databases ' + database]),
        ('erpnext-sites.tar.gz', ['docker', 'exec', '-u', '0', 'rsi-lab-erpnext-backend-1', 'tar', 'czf', '-', '-C', '/home/frappe/frappe-bench', 'sites']),
        ('zammad.dump', ['docker', 'exec', 'rsi-lab-zammad-zammad-postgresql-1', 'pg_dump', '-U', 'zammad', '-Fc', 'zammad_production']),
        ('zammad-storage.tar.gz', ['docker', 'exec', 'rsi-lab-zammad-zammad-railsserver-1', 'tar', 'czf', '-', '-C', '/opt/zammad', 'storage']),
    ]
    manifest = {'createdAtUtc': datetime.utcnow().isoformat() + 'Z', 'erpnextDatabase': database, 'files': []}
    for filename, command in commands:
        path = target / filename
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            subprocess.run(command, stdout=output, check=True, timeout=180)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        result = {'file': filename, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}
        if not result['bytes']:
            raise RuntimeError('Empty backup: ' + filename)
        manifest['files'].append(result)
        print(json.dumps(result), flush=True)
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Snapshot saved: ' + str(target))


if __name__ == '__main__':
    main()
