#!/usr/bin/env python3
"""Bounded HTTP checks against copied TeachingOpen release configs and official Nginx.
Writes only below its own artifact directory and stops/removes only its own labeled container.
"""
import argparse
import datetime
import difflib
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import socket
import sys
import subprocess
import time
import uuid
from urllib.parse import urlsplit

ARTIFACT = Path(__file__).resolve().parent
DOCKER = shutil.which('docker') or '/usr/local/bin/docker'
IMAGE = 'nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94'
PORTS = (18186, 18187)
TOKEN = 'nginx-contract-canary-' + uuid.uuid4().hex[:12]
PYTHON_RUNTIME_ASSETS = [
    'runner.css', 'runner-loader.js', 'static/js/vendor.js', 'static/js/app.js',
    'turtle-renderer.js', 'runner.js', 'worker-turtle.js', 'worker.js',
]
SECURITY_HEADERS = {
    'X-Frame-Options': 'SAMEORIGIN',
    'X-Content-Type-Options': 'nosniff',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Content-Security-Policy': "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: ws: wss:;",
    'X-Download-Options': 'noopen',
    'X-Permitted-Cross-Domain-Policies': 'none',
    'Permission-Policy': 'camera=(), geolocation=(), microphone=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
}


def command(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=90)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {result.stderr.strip()}')
    return result


def free_ports(wait_seconds=0):
    for port in PORTS:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                with socket.socket() as probe_socket:
                    probe_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe_socket.bind(('127.0.0.1', port))
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)


def request(port, method, path, security_headers=False):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
    try:
        connection.request(method, path, headers={'X-Probe-Canary': TOKEN})
        response = connection.getresponse()
        response.read()  # Discard all response bodies; only canary metadata is retained.
        if security_headers:
            names = [*SECURITY_HEADERS, 'Cross-Origin-Resource-Policy']
            return {'status': response.status,
                    'headers': {name: response.getheader(name) for name in names}}
        raw_location = response.getheader('Location')
        redirect = urlsplit(raw_location) if raw_location else None
        location_path = (redirect.path + ('?' + redirect.query if redirect.query else '')) if redirect else None
        return {
            'raw_location': raw_location,
            'status': response.status,
            'location': location_path,
            'upstream_method': response.getheader('X-Probe-Method'),
            'upstream_path': response.getheader('X-Probe-Path'),
            'upstream_canary_matches': response.getheader('X-Probe-Canary') == TOKEN,
        }
    finally:
        connection.close()


def copied_config(source, dest):
    original = source.read_text()
    mapped = original.replace('listen 80 default_server;', 'listen 8080 default_server;', 1)
    roots = ['/usr/share/nginx/html', '/www/wwwroot/localhost']
    root_hits = 0
    for root in roots:
        count = mapped.count('root ' + root + ';')
        root_hits += count
        mapped = mapped.replace('root ' + root + ';', 'root /probe/fixture/public;')
    assert root_hits == 1
    upstream_hits = 0
    for upstream in ['http://api:8080', 'http://127.0.0.1:8080']:
        count = mapped.count(upstream)
        upstream_hits += count
        mapped = mapped.replace(upstream, 'http://127.0.0.1:8081')
    assert upstream_hits == 1
    assert original != mapped
    dest.write_text(mapped)
    dest.with_suffix('.environment.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(keepends=True), mapped.splitlines(keepends=True),
        fromfile=str(source), tofile=str(dest))))
    return hashlib.sha256(original.encode()).hexdigest()


def cases():
    good = []

    def add(method, path, status, upstream_path, purpose, location=None):
        good.append((method, path, status, upstream_path, purpose, location))

    ordinary = '/api/probe?cursor=%2F&text=a%20b'
    for method in ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'OPTIONS']:
        add(method, ordinary, 204, ordinary, 'API method and URI preserved')
    for path in ['/api/', '/api/probe%20encoded?x=%252F&y=a+b',
                 '/api/probe%2Fencoded?x=a%2Fb', '/api/probe.map', '/api/probe.sql',
                 '/api/logfiles/probe', '/api/samples/probe',
                 '/api/%E8%AF%BE%E7%A8%8B', '/api//probe',
                 '/api/probe?dup=a&dup=b&empty=&text=a%20b+z&hash=%23']:
        add('GET', path, 204, path, 'API path, Unicode encoding, query preserved')
    for method in ['GET', 'POST', 'PUT', 'DELETE']:
        for path in ['/api', '/api?cursor=%2F&text=a%20b']:
            target = '/api/' + (path[4:] if '?' in path else '')
            add(method, path, 308, None, 'Bare API redirect retains query and method', target)
    for path in ['/apiculture', '/apiXYZ/probe?cursor=%2F']:
        for method in ['GET', 'HEAD', 'POST', 'PUT', 'DELETE']:
            add(method, path, 200 if method in ['GET', 'HEAD'] else 405,
                None, 'Non-API prefix stays in frontend location')
    for method in ['GET', 'HEAD']:
        for path in ['/index.html', '/probe.js', '/course/unit/1']:
            add(method, path, 200, None, 'Static file and SPA fallback')
    for path in ['/probe.js.map', '/probe.sql', '/logfiles/probe', '/samples/probe']:
        add('GET', path, 404, None, 'Static sensitive content denied')
    for path in ['/../outside-probe.txt', '/%2e%2e/outside-probe.txt']:
        add('GET', path, 400, None, 'Out-of-root traversal rejected')
    for method in ['TRACE', 'TRACK', 'MOVE', 'COPY', 'PROPFIND', 'SEARCH', 'MKCOL', 'LOCK', 'UNLOCK', 'PROPPATCH']:
        add(method, '/api/probe', 405, None, 'Previously denied unsupported method remains denied')
    for method in ['POST', 'PUT', 'DELETE', 'OPTIONS']:
        add(method, '/probe.js', 405, None, 'Static file disallows write method')
    return good


def resource_policy_cases():
    for asset in PYTHON_RUNTIME_ASSETS:
        for method in ['GET', 'HEAD']:
            for suffix in ['', '?v=runtime-check']:
                yield method, '/python/' + asset + suffix, 200, 'cross-origin'
    for path in ['/index.html', '/python/index.html', '/python/player.html',
                 '/python/execution.js', '/python/private.py', '/python/runner.js.bak',
                 '/python/runner.js/extra', '/scratch3/runner.js']:
        yield 'GET', path, 200, 'same-site'
    yield 'GET', '/python/runner.js.map', 404, 'same-site'
    yield 'GET', '/api/python/runner.js', 204, 'same-site'
    yield 'GET', '/api/sys/common/static/python/private.py', 204, 'same-site'


def run_config(label, source, prefix):
    run_dir = ARTIFACT / prefix / label
    run_dir.mkdir(parents=True, exist_ok=False)
    copy_path = run_dir / 'server.conf'
    source_hash = copied_config(source, copy_path)
    relative_server = copy_path.relative_to(ARTIFACT)
    main = '''worker_processes 1;
error_log /dev/stderr notice;
pid /tmp/nginx-contract.pid;
events { worker_connections 128; }
http {
    log_format probe '$request_method $request_uri $status';
    access_log /dev/stdout probe;
    client_body_temp_path /tmp/probe-client-temp;
    proxy_temp_path /tmp/probe-proxy-temp;
    fastcgi_temp_path /tmp/probe-fastcgi-temp;
    uwsgi_temp_path /tmp/probe-uwsgi-temp;
    scgi_temp_path /tmp/probe-scgi-temp;
    include /etc/nginx/mime.types;
    include /probe/''' + str(relative_server) + ''';
    server {
        listen 8081;
        server_name mock-echo;
        add_header X-Probe-Method $request_method always;
        add_header X-Probe-Path $request_uri always;
        add_header X-Probe-Canary $http_x_probe_canary always;
        return 204;
    }
}
'''
    config_path = run_dir / 'nginx.conf'
    config_path.write_text(main)
    container_name = 'teachingopen-nginx-contract-' + uuid.uuid4().hex[:12]
    label_value = uuid.uuid4().hex
    config_in_container = '/probe/' + str(config_path.relative_to(ARTIFACT))
    inspection = command(DOCKER, 'run', '--rm', '--entrypoint', '/usr/sbin/nginx',
                         '--network', 'none', '--mount', f'type=bind,src={ARTIFACT},dst=/probe,readonly',
                         IMAGE, '-t', '-c', config_in_container)
    (run_dir / 'config-test.log').write_text(inspection.stdout + inspection.stderr)
    free_ports()
    launched = command(DOCKER, 'run', '-d', '--name', container_name,
                       '--label', 'teachingopen.nginx.contract=' + label_value,
                       '--user', '101:101', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                       '-p', '127.0.0.1:18186:8080', '-p', '127.0.0.1:18187:8081',
                       '--mount', f'type=bind,src={ARTIFACT},dst=/probe,readonly',
                       '--entrypoint', '/usr/sbin/nginx', IMAGE,
                       '-c', config_in_container, '-g', 'daemon off;')
    container_id = launched.stdout.strip()
    receipt = {'container_id': container_id, 'container_name': container_name,
               'owner_label': label_value, 'source': str(source), 'source_sha256': source_hash,
               'ports': {'nginx': '127.0.0.1:18186', 'echo': '127.0.0.1:18187'},
               'config_file': str(copy_path), 'environment_diff': str(copy_path.with_suffix('.environment.diff'))}
    try:
        for _ in range(40):
            try:
                if request(18187, 'GET', '/ready')['status'] == 204:
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError('Owned synthetic echo did not become ready')
        actual_inspect = json.loads(command(DOCKER, 'inspect', container_id).stdout)[0]
        receipt['daemon_port_bindings'] = actual_inspect['HostConfig']['PortBindings']
        receipt['nginx_version'] = command(DOCKER, 'exec', container_id, '/usr/sbin/nginx', '-v').stderr.strip()
        rows = []
        for method, path, status, upstream_path, purpose, location in cases():
            observed = request(18186, method, path)
            raw_location = observed.pop('raw_location')
            expected = {'status': status, 'location': location, 'upstream_method': method if upstream_path is not None else None,
                        'upstream_path': upstream_path,
                        'upstream_canary_matches': upstream_path is not None}
            follow_expected = None
            follow_observed = None
            if location is not None:
                follow_expected = {'status': 204, 'location': None, 'upstream_method': method,
                                   'upstream_path': location, 'upstream_canary_matches': True}
                if observed['status'] == 308 and observed['location'] == location:
                    follow_observed = request(18186, method, location)
                    follow_observed.pop('raw_location')
            row = {'method': method, 'request_path': path, 'purpose': purpose,
                   'expected': expected, 'actual': observed, 'raw_location': raw_location,
                   'redirect_follow_expected': follow_expected,
                   'redirect_follow_actual': follow_observed,
                   'pass': expected == observed and follow_expected == follow_observed}
            rows.append(row)
        for method, path, status, policy in resource_policy_cases():
            observed = request(18186, method, path, security_headers=True)
            expected = {'status': status,
                        'headers': {**SECURITY_HEADERS, 'Cross-Origin-Resource-Policy': policy}}
            rows.append({'method': method, 'request_path': path,
                         'purpose': 'Opaque Python runtime exception preserves all other security headers',
                         'expected': expected, 'actual': observed, 'pass': observed == expected})
        report = {'receipt': receipt, 'total': len(rows),
                  'passed': sum(row['pass'] for row in rows),
                  'failed': sum(not row['pass'] for row in rows), 'rows': rows}
        (run_dir / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        return report
    finally:
        identity = json.loads(command(DOCKER, 'inspect', container_id).stdout)[0]
        assert identity['Id'] == container_id
        assert identity['Config']['Labels']['teachingopen.nginx.contract'] == label_value
        logs = command(DOCKER, 'logs', container_id)
        (run_dir / 'nginx-access-and-error.log').write_text(logs.stdout + logs.stderr)
        command(DOCKER, 'stop', '--time', '3', container_id)
        stopped = json.loads(command(DOCKER, 'inspect', container_id).stdout)[0]
        assert stopped['State']['Running'] is False
        command(DOCKER, 'rm', container_id)
        free_ports(wait_seconds=10)
        (run_dir / 'shutdown.json').write_text(json.dumps({
            'container_id': container_id, 'owner_label_checked': True,
            'stopped': True, 'removed': True, 'host_ports_free_after_shutdown': list(PORTS)
        }, indent=2) + '\n')


def main():
    global IMAGE, ARTIFACT, DOCKER
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', '--candidate', dest='candidate', type=Path,
                        default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--expect-pass', action='store_true')
    parser.add_argument('--prefix', default='run')
    parser.add_argument('--image', default=IMAGE)
    parser.add_argument('--docker', default=DOCKER)
    args = parser.parse_args()
    IMAGE = args.image
    DOCKER = args.docker
    args.candidate = args.candidate.resolve()
    ARTIFACT = args.output_dir.resolve()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    free_ports()
    fixture = ARTIFACT / 'fixture/public'
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / 'index.html').write_text('<!doctype html><title>TeachingOpen synthetic SPA</title>SPA canary\n')
    (fixture / 'probe.js').write_text('/* synthetic static canary */\n')
    for path in [*['python/' + asset for asset in PYTHON_RUNTIME_ASSETS],
                 'python/index.html', 'python/player.html', 'python/execution.js',
                 'python/private.py', 'python/runner.js.bak', 'scratch3/runner.js']:
        resource = fixture / path
        resource.parent.mkdir(exist_ok=True, parents=True)
        resource.write_text('/* synthetic resource policy canary */\n')
    for path in ['probe.js.map', 'probe.sql', 'logfiles/probe', 'samples/probe']:
        denied = fixture / path
        denied.parent.mkdir(exist_ok=True, parents=True)
        denied.write_text('synthetic denied canary\n')
    (ARTIFACT / 'fixture/outside-probe.txt').write_text('synthetic out-of-root canary\n')
    image_metadata = json.loads(command(DOCKER, 'image', 'inspect', IMAGE).stdout)[0]
    image_receipt = {
        'image_tag': IMAGE, 'image_id': image_metadata['Id'],
        'repo_digests': image_metadata['RepoDigests'],
        'architecture': image_metadata['Architecture'], 'os': image_metadata['Os'],
        'server': command(DOCKER, 'version', '--format', '{{.Server.Version}}').stdout.strip(),
        'context': command(DOCKER, 'context', 'show').stdout.strip(),
        'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    directory = ARTIFACT / args.prefix
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'contract-cases.json').write_text(json.dumps(cases(), indent=2) + '\n')
    (directory / 'image-receipt.json').write_text(json.dumps(image_receipt, indent=2) + '\n')
    reports = [run_config(label, args.candidate / rel, args.prefix) for label, rel in [
        ('docker-release', 'web/nginx/default.conf'), ('native-example', '资料/nginx.example.conf')]]
    summary = {r['receipt']['source']: {'passed': r['passed'], 'failed': r['failed'], 'total': r['total']} for r in reports}
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if args.expect_pass and any(r['failed'] for r in reports) else 0


if __name__ == '__main__':
    sys.exit(main())
