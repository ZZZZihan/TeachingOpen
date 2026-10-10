#!/usr/bin/env python3
"""Opt-in IP TLS configs and bounded, reversible Nginx configuration switching.

Rendering is offline. Activation is an explicit host operation: it neither obtains
certificates nor installs packages, changes firewall rules, or edits application data.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

KIND = 'teachingopen-ip-https-v1'
TEMPLATE = Path(__file__).resolve().parents[1] / 'web/nginx/default.conf'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ordinary(value, directory=False, missing=False):
    path = Path(os.path.abspath(value))
    for part in (*reversed(path.parents), path):
        if missing and part == path and not part.exists() and not part.is_symlink():
            continue
        mode = part.lstat().st_mode
        expected = stat.S_ISDIR if directory or part != path else stat.S_ISREG
        if stat.S_ISLNK(mode) or not expected(mode):
            raise ValueError('Expected an ordinary path without symlink components: ' + str(path))
    return path


def safe_config_path(value):
    # Paths are quoted in Nginx, but still reject expansion and control syntax.
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or '..' in Path(value).parts:
        raise ValueError('Nginx paths must be absolute, without spaces or shell/config syntax')
    return str(Path(value))


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Nginx source template changed; review its rendering anchor')
    return text.replace(old, new, 1)


def reviewed_site_profile(template, ip, web_root, api_upstream):
    """The one supported native-site shape, not a general Nginx parser.

    Review a different shape before extending these explicit anchors. A caller's
    digest proves which bytes were reviewed; this profile also prevents unknown
    listeners, nested servers, includes or TLS/proxy policies from being copied.
    """
    source = '''map $uri $teaching_html_cache_policy {
    default "";
    ~*\\.html$ "no-cache";
}

''' + template
    source = replace_once(source, '    listen 80 default_server;',
                          '    listen 80 default_server;\n    listen 127.0.0.1:8088;')
    source = replace_once(source, '    server_name localhost;', '    server_name ' + ip + ';')
    source = replace_once(source, 'root /usr/share/nginx/html;', 'root ' + web_root + ';')
    source = replace_once(source, 'proxy_pass              http://api:8080;',
                          'proxy_pass              ' + api_upstream + ';')
    source = replace_once(source,
        '    add_header Cross-Origin-Resource-Policy $teaching_python_resource_policy always;',
        '    add_header Cross-Origin-Resource-Policy $teaching_python_resource_policy always;\n'
        '    add_header Cache-Control $teaching_html_cache_policy always;')
    return replace_once(source, '    location / {', '''    # A missing script/style is not a client-side page route.
    location ~* \\.(js|css)(\\.gz)?$ {
        root ''' + web_root + ''';
        try_files $uri =404;
        gzip on;
        gzip_min_length 1k;
        gzip_comp_level 9;
        gzip_types application/javascript text/css;
        gzip_vary on;
        gzip_disable "MSIE [1-6]\\.";
    }

    location / {''')


def checked_sha256(value):
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Use an explicit lowercase SHA-256 digest')
    return value


def atomic_write(path, data, mode=0o600, owner=None):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            if owner is not None:
                os.fchown(stream.fileno(), *owner)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_receipt(backup, receipt):
    atomic_write(backup / 'receipt.json', (json.dumps(receipt, indent=2) + '\n').encode())


def acme_location(acme_root):
    return '''    location ^~ /.well-known/acme-challenge/ {
        root "''' + acme_root + '''";
        default_type text/plain;
        try_files $uri =404;
    }

'''


def render(ip, web_root, api_upstream, acme_root, certificate, private_key, output,
           source_config=None, source_sha256=None):
    address = ipaddress.ip_address(ip)
    if address.version != 4 or not address.is_global or address.is_multicast:
        raise ValueError('A globally routable public IPv4 address is required')
    ip = str(address)
    match = re.fullmatch(r'http://(127\.0\.0\.1):([0-9]+)', api_upstream)
    if not match or not 1 <= int(match[2]) <= 65535:
        raise ValueError('Use an explicit same-host http://127.0.0.1:PORT upstream')
    web_root, acme_root, certificate, private_key = [safe_config_path(value) for value in
        (web_root, acme_root, certificate, private_key)]
    if certificate == private_key:
        raise ValueError('Certificate and private key must have distinct paths')
    for secret in (Path(certificate), Path(private_key)):
        for public in (Path(web_root), Path(acme_root)):
            if secret == public or public in secret.parents:
                raise ValueError('Certificate material must stay outside public web roots')
    output = ordinary(output, directory=True, missing=True)
    if output.exists():
        raise ValueError('Output must be a new directory')
    for public in (Path(web_root), Path(acme_root)):
        if output == public or public in output.parents:
            raise ValueError('Output must stay outside public web roots')
    if (source_config is None) != (source_sha256 is None):
        raise ValueError('Provide both source configuration and its reviewed SHA-256')
    template = ordinary(TEMPLATE).read_bytes()
    source_path = ordinary(source_config) if source_config is not None else ordinary(TEMPLATE)
    source_bytes = source_path.read_bytes()
    source = source_bytes.decode('utf-8')
    native = source_config is not None
    if native:
        if digest(source_bytes) != checked_sha256(source_sha256):
            raise ValueError('Reviewed source configuration checksum mismatch')
        if source != reviewed_site_profile(template.decode('utf-8'), ip, web_root, api_upstream):
            raise ValueError('Reviewed source does not match the supported single-server site profile; '
                             'review its paths, listeners and unique rendering anchors')
    if source.count('\nserver\n{\n') != 1:
        raise ValueError('Expected exactly one reviewed application server block')
    prefix, server = source.split('\nserver\n', 1)
    server = 'server\n' + server
    if not native:
        server = replace_once(server, '    server_name localhost;', '    server_name ' + ip + ';')
        server = replace_once(server, 'root /usr/share/nginx/html;', 'root "' + web_root + '";')
        server = replace_once(server, 'proxy_pass              http://api:8080;', 'proxy_pass              ' + api_upstream + ';')
    server = replace_once(server, 'proxy_set_header        Host $host;', '''proxy_set_header        Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Host $host;''')
    server = replace_once(server, '    location / {', acme_location(acme_root) + '    location / {')
    server = replace_once(server, '    location = /api {', '    location = /api {\n        absolute_redirect off;')
    server = replace_once(server, 'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;',
                          'proxy_set_header X-Forwarded-For $remote_addr;')
    # Avoid permanent browser state while this configuration remains a trial.
    if 'Strict-Transport-Security' in source or 'ssl_certificate' in source:
        raise ValueError('Source template unexpectedly contains TLS policy')
    # The trial's HTTP block owns 8088; duplicating it into TLS would conflict.
    tls_source = replace_once(server, '    listen 127.0.0.1:8088;\n', '') if native else server
    tls = replace_once(tls_source, '    listen 80 default_server;', '''    listen 443 ssl;
    ssl_certificate "''' + certificate + '''";
    ssl_certificate_key "''' + private_key + '''";
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:TeachingOpenIpTLS:10m;
    ssl_session_timeout 1d;''')
    redirect = '''server {
    listen 80 default_server;
    server_name ''' + ip + ''';
''' + acme_location(acme_root) + '''    # Never redirect an API request or a body-bearing method already sent over HTTP.
    location = /api { return 426; }
    location ^~ /api/ { return 426; }
    location / {
        if ($request_method !~ ^(GET|HEAD)$) { return 426; }
        add_header Cache-Control "no-store" always;
        return 307 https://''' + ip + '''$request_uri;
    }
}
'''
    # Final external HTTP policy must not remove the local business/health entry.
    local_http = '\n' + replace_once(server, '    listen 80 default_server;\n', '') if native else ''
    generated = {
        'bootstrap.conf': prefix + '\n' + server,
        'trial.conf': prefix + '\n' + server + '\n' + tls,
        'https.conf': prefix + '\n' + tls + local_http + '\n' + redirect,
    }
    output.mkdir(mode=0o700)
    files = {}
    for name, content in generated.items():
        data = ('# Generated by TeachingOpen ip_https.py; install only after target review.\n' + content).encode()
        atomic_write(output / name, data)
        files[name] = {'sha256': digest(data), 'bytes': len(data)}
    manifest = {'kind': KIND, 'public_ipv4': ip, 'template_sha256': digest(template),
        'source_mode': 'reviewed_site' if native else 'repository_template',
        'source_path': str(source_path), 'source_sha256': digest(source_bytes),
        'files': files, 'deployed': False, 'certificate_issued': False,
        'production_verified': False}
    save_receipt(output, manifest)
    # A render manifest is deliberately distinct from an activation receipt.
    (output / 'receipt.json').rename(output / 'manifest.json')
    return {'output': str(output), 'manifest_sha256': digest((output / 'manifest.json').read_bytes()), **manifest}


def nginx_command(nginx, *args):
    result = subprocess.run([str(nginx), *args], capture_output=True, timeout=60)
    if result.returncode:
        # Host configuration diagnostics can contain private paths or credentials.
        raise RuntimeError('Nginx ' + ' '.join(args) + ' failed; exit=' + str(result.returncode))


@contextmanager
def target_lock(target):
    lock = target.with_name('.' + target.name + '.teachingopen-https.lock')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Unsafe configuration lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another HTTPS configuration operation holds the lock') from None
        yield
    finally:
        os.close(fd)


def executable(value):
    if not Path(value).is_absolute():
        raise ValueError('Provide an absolute Nginx executable path')
    path = ordinary(value)
    if not os.access(path, os.X_OK):
        raise ValueError('Nginx path is not executable')
    return path


def distinct(backup, *paths):
    for path in paths:
        if path == backup or path in backup.parents or backup in path.parents:
            raise ValueError('Backup directory overlaps a configuration or executable path')


def switch(target, next_data, restore_data, mode, owner, nginx, backup, receipt, success, recovered):
    try:
        atomic_write(target, next_data, mode, owner)
        nginx_command(nginx, '-t')
        nginx_command(nginx, '-s', 'reload')
    except (Exception, KeyboardInterrupt) as error:
        try:
            atomic_write(target, restore_data, mode, owner)
            nginx_command(nginx, '-t')
            nginx_command(nginx, '-s', 'reload')
        except (Exception, KeyboardInterrupt):
            receipt['status'] = 'recovery_required'
            save_receipt(backup, receipt)
            raise RuntimeError('Switch and recovery failed; inspect target and private backup') from None
        receipt['status'] = recovered
        save_receipt(backup, receipt)
        raise RuntimeError('Switch failed (' + str(error) + '); previous configuration bytes restored and reloaded') from None
    receipt['status'] = success
    save_receipt(backup, receipt)
    return {'status': success, 'target': str(target), 'backup': str(backup),
            'active_sha256': digest(next_data), 'live_business_verified': False}


def activate(target, candidate, backup, nginx, expected_target_sha256=None):
    target, candidate = ordinary(target), ordinary(candidate)
    nginx = executable(nginx)
    backup = ordinary(backup, directory=True, missing=True)
    if backup.exists() or target == candidate:
        raise ValueError('Use a fresh backup directory and a distinct candidate file')
    distinct(backup, target, candidate, nginx)
    if expected_target_sha256 is not None:
        checked_sha256(expected_target_sha256)
    with target_lock(target):
        target, candidate = ordinary(target), ordinary(candidate)
        old, new = target.read_bytes(), candidate.read_bytes()
        if expected_target_sha256 is not None and digest(old) != expected_target_sha256:
            raise ValueError('Target changed since review; expected target checksum mismatch')
        info = target.stat()
        nginx_command(nginx, '-t')
        backup.mkdir(mode=0o700)
        atomic_write(backup / 'previous.conf', old)
        receipt = {'kind': KIND, 'status': 'switching', 'target': str(target), 'nginx': str(nginx),
            'created_at': datetime.now(timezone.utc).isoformat(), 'previous_sha256': digest(old),
            'candidate_sha256': digest(new), 'mode': stat.S_IMODE(info.st_mode),
            'uid': info.st_uid, 'gid': info.st_gid}
        save_receipt(backup, receipt)
        return switch(target, new, old, receipt['mode'], (info.st_uid, info.st_gid), nginx,
                      backup, receipt, 'active', 'activation_failed_recovered')


def rollback(target, backup, nginx):
    target, backup = ordinary(target), ordinary(backup, directory=True)
    nginx = executable(nginx)
    distinct(backup, target, nginx)
    if stat.S_IMODE(backup.stat().st_mode) != 0o700:
        raise ValueError('Backup directory must be private (0700)')
    with target_lock(target):
        record = ordinary(backup / 'receipt.json')
        previous = ordinary(backup / 'previous.conf')
        if any(stat.S_IMODE(path.stat().st_mode) != 0o600 for path in (record, previous)):
            raise ValueError('Backup files must be private (0600)')
        receipt = json.loads(record.read_text())
        if receipt.get('kind') != KIND or receipt.get('target') != str(target) or receipt.get('nginx') != str(nginx):
            raise ValueError('Backup does not belong to this target and Nginx executable')
        old, active = previous.read_bytes(), ordinary(target).read_bytes()
        if digest(old) != receipt.get('previous_sha256'):
            raise ValueError('Original configuration backup checksum mismatch')
        if receipt.get('status') == 'rolled_back' and digest(active) == digest(old):
            return {'status': 'rolled_back', 'target': str(target), 'backup': str(backup),
                    'active_sha256': digest(old), 'live_business_verified': False}
        state = receipt.get('status')
        expected = {receipt.get('candidate_sha256')} if state == 'active' else set()
        if state in ('switching', 'rolling_back', 'recovery_required'):
            # SIGTERM/SIGKILL may stop the operation before or after its atomic
            # replace. Recovery is an explicit rollback, never an automatic claim.
            expected = {receipt.get('candidate_sha256'), receipt.get('previous_sha256')}
        if digest(active) not in expected:
            raise ValueError('Target changed or operation is incomplete; inspect before manual recovery')
        receipt['status'] = 'rolling_back'
        save_receipt(backup, receipt)
        # A missing current certificate can make `nginx -t` fail. Check the
        # restored configuration, rather than requiring the broken one to pass.
        return switch(target, old, active, receipt['mode'], (receipt['uid'], receipt['gid']),
                      nginx, backup, receipt, 'rolled_back', 'active')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    rendering = commands.add_parser('render')
    for name in ('ip', 'web-root', 'api-upstream', 'acme-root', 'certificate', 'private-key', 'output'):
        rendering.add_argument('--' + name, required=True)
    rendering.add_argument('--source-config', help='Reviewed native-site config; paired with --source-sha256')
    rendering.add_argument('--source-sha256', help='Exact reviewed source bytes; both source options are required together')
    for action in ('activate', 'rollback'):
        command = commands.add_parser(action)
        for name in ('target', 'backup', 'nginx'):
            command.add_argument('--' + name, required=True)
        if action == 'activate':
            command.add_argument('--candidate', required=True)
            command.add_argument('--expected-target-sha256', help='Refuse activation if target changed since review')
    args = vars(parser.parse_args())
    action = args.pop('action')
    try:
        print(json.dumps(globals()[action](**args), indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
