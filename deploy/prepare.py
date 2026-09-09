#!/usr/bin/env python3
"""Prepare isolated business-platform Compose projects from pinned upstream sources.

No Docker access needed for preparation. Passwords are generated once and kept in
private ignored .env files; generated manifests never embed those passwords.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import urllib.request

UPSTREAM = {
    'erpnext': ('frappe/frappe_docker', 'a0c52135d4d41c4b8acf7adfdfc5bbcba46dd4d0', 'pwd.yml'),
    'zammad': ('zammad/zammad-docker-compose', '27944f87aed91420242dfa97038ff96555d7cbe7', 'docker-compose.yml'),
}


def replace_exact(source, old, new, count=1):
    actual = source.count(old)
    if actual != count:
        raise ValueError('Pinned source changed: expected {} occurrences, got {}'.format(count, actual))
    return source.replace(old, new)


def adapt_erpnext(source):
    source = replace_exact(source, 'MYSQL_ROOT_PASSWORD: admin', 'MYSQL_ROOT_PASSWORD: ${DB_PASSWORD:?run prepare.py}', 2)
    source = replace_exact(source, 'MARIADB_ROOT_PASSWORD: admin', 'MARIADB_ROOT_PASSWORD: ${DB_PASSWORD:?run prepare.py}', 2)
    source = replace_exact(source, '--admin-password=admin', '--admin-password="$$ADMIN_PASSWORD"')
    source = replace_exact(source, '--db-root-password=admin', '--db-root-password="$$DB_PASSWORD"')
    source = replace_exact(source, '  create-site:\n', '  create-site:\n    environment:\n      ADMIN_PASSWORD: ${ADMIN_PASSWORD:?run prepare.py}\n      DB_PASSWORD: ${DB_PASSWORD:?run prepare.py}\n')
    source = replace_exact(source, '"8080:8080"', '"127.0.0.1:18080:8080"')
    return source


def adapt_zammad(source):
    source = replace_exact(source, '  zammad-elasticsearch:\n', '  zammad-elasticsearch:\n    profiles: ["search"]\n')
    source = replace_exact(source, '  zammad-backup:\n    <<:', '  zammad-backup:\n    profiles: ["backup"]\n    <<:')
    source = replace_exact(source, '${POSTGRES_PASS:-zammad}', '${POSTGRES_PASS:?run prepare.py}', 2)
    source = replace_exact(source, '"${NGINX_EXPOSE_PORT:-8080}:${NGINX_PORT:-8080}"', '"127.0.0.1:18081:${NGINX_PORT:-8080}"')
    return source


def write_private_once(path, content):
    if path.exists():
        return
    descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'runtime')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for platform, (repository, revision, filename) in UPSTREAM.items():
        directory = args.output / platform
        directory.mkdir(exist_ok=True, mode=0o700)
        url = 'https://raw.githubusercontent.com/{}/{}/{}'.format(repository, revision, filename)
        request = urllib.request.Request(url, headers={'User-Agent': 'rsi-agent-lab-deployment'})
        upstream = urllib.request.urlopen(request, timeout=30).read()
        source = upstream.decode('utf-8')
        rendered = adapt_erpnext(source) if platform == 'erpnext' else adapt_zammad(source)
        (directory / 'compose.yaml').write_text(rendered, encoding='utf-8')
        (directory / 'source.json').write_text(json.dumps({'repository': repository, 'revision': revision, 'url': url, 'upstream_sha256': hashlib.sha256(upstream).hexdigest()}, indent=2) + '\n')
        if platform == 'erpnext':
            values = {'COMPOSE_PROJECT_NAME': 'rsi-lab-erpnext', 'DB_PASSWORD': secrets.token_hex(24), 'ADMIN_PASSWORD': secrets.token_hex(24)}
        else:
            values = {'COMPOSE_PROJECT_NAME': 'rsi-lab-zammad', 'POSTGRES_PASS': secrets.token_hex(24), 'VERSION': '7.1.3-0011', 'TZ': 'Asia/Shanghai', 'ELASTICSEARCH_ENABLED': 'false', 'BACKUP_ON_START': 'false', 'RESTART': 'unless-stopped', 'ZAMMAD_FQDN': '127.0.0.1:18081', 'ZAMMAD_HTTP_TYPE': 'http'}
        write_private_once(directory / '.env', ''.join('{}={}\n'.format(key, value) for key, value in values.items()))
        print('Prepared {}: {} (credentials preserved if already present)'.format(platform, directory))


if __name__ == '__main__':
    main()
