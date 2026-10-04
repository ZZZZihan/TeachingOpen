#!/usr/bin/env python3
"""Bounded real Linux-container HTTP probe for one fresh owned release bundle.

This file is prepared without starting services. Root executes it explicitly.
CAPTCHA cache access is solely for synthetic API fixture login, never browser
login acceptance. Reports contain booleans, response codes and hashes only.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ACTORS = ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')
CASES = (
    'frozen_bundle_verified', 'four_owned_running_containers',
    'owned_dual_network_isolation', 'only_web_loopback_18190_published',
    'exact_bundle_bind_mounts_with_readonly_jar_dist', 'pinned_linux_images_match_containers',
    'actual_health_up', 'index_matches_frozen_body', 'referenced_asset_matches_frozen_body',
    'anonymous_home_courses', 'invalid_api_token_401',
    *('fixture_login_and_role_menu_' + a for a in ACTORS),
    'student_same_class_course_read', 'student_foreign_class_course_denied',
    'admin_post_course_persisted', 'admin_post_unit_persisted',
    'admin_put_course_success', 'admin_put_unit_success',
    'edited_course_api_and_db_reread', 'edited_unit_api_and_db_reread',
    'student_put_denied_and_both_values_unchanged',
    'admin_delete_unit_persisted', 'admin_delete_course_persisted',
    'anonymous_public_cover_get_bytes_nosniff', 'anonymous_public_cover_head_size_nosniff',
    'anonymous_public_cover_range_original_bytes',
    'student_private_video_get_bytes_nosniff', 'student_private_video_head_size_nosniff',
    'student_private_video_range_original_bytes', 'foreign_private_video_denied',
    'student_real_multipart_python_upload', 'student_file_registration_and_db_owner',
    'student_personal_python_draft_submit', 'python_draft_db_identity_status_persisted',
    'student_python_draft_reopens', 'python_attachment_download_full_hash',
    'foreign_python_draft_and_download_denied',
    'media_cookie_httponly_path_samesite_and_media_read',
    'media_cookie_cannot_authorize_api', 'logout_revokes_token_and_media_cookie',
    'actual_websocket_upgrade_and_authentication_reply',
)
assert len(CASES) == 45


def sha(value):
    return hashlib.sha256(value).hexdigest()


def run(command, input_bytes=None, timeout=30):
    """Never put subprocess stderr, command output or secrets into a report."""
    result = subprocess.run(command, input=input_bytes, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Subprocess failed; diagnostics intentionally withheld')
    return result.stdout


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError('Private ordinary config required')
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            fd = None
            return json.load(stream)
    finally:
        if fd is not None:
            os.close(fd)


def prepare_output(path):
    """Validate the report target before traffic; never chmod existing paths."""
    output = Path(path).absolute()
    try:
        output.lstat()
    except FileNotFoundError:
        pass
    else:
        raise ValueError('Output must be a new private report')
    parent = output.parent
    try:
        info = parent.lstat()
    except FileNotFoundError:
        parent.mkdir(mode=0o700, parents=True)
        info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise ValueError('Report directory must already be an ordinary private directory')
    if info.st_mode & (stat.S_IWUSR | stat.S_IXUSR) != stat.S_IWUSR | stat.S_IXUSR:
        raise ValueError('Private report directory must permit owner write and traversal')
    return output


def literal(value):
    """Read-only SQL values use a hex literal, avoiding shell/SQL interpolation."""
    return 'CONVERT(0x' + value.encode('utf-8').hex() + ' USING utf8mb4)'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Probe refuses redirects')


class Api:
    def __init__(self, credentials, containers):
        self.base = 'http://127.0.0.1:18190'
        self.credentials = credentials
        self.containers = containers
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.tokens = {}
        self.cookies = {}
        self.cookie_headers = {}

    def http(self, method, path, actor=None, data=None, headers=None, token=None):
        if not path.startswith('/') or path.startswith('//') or urlsplit(path).netloc:
            raise ValueError('Only relative same-origin probe paths allowed')
        hdr = dict(headers or {})
        if actor is not None:
            hdr['X-Access-Token'] = self.tokens[actor]
        elif token is not None:
            hdr['X-Access-Token'] = token
        if data is not None and not isinstance(data, bytes):
            hdr['Content-Type'] = 'application/json'
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        try:
            response = self.opener.open(Request(self.base + path, data=data, headers=hdr, method=method), timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError('Probe response limit exceeded')
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                body = None
            return response.status, body, response.headers, raw

    def api(self, method, path, actor=None, data=None, headers=None, token=None):
        return self.http(method, '/api' + path, actor, data, headers, token)

    def redis(self, *arguments):
        # Password and commands travel on stdin to redis-cli --raw. No auth argv,
        # environment variables, shell expansion or redis-cli credential warning.
        # Both password and fixture command arguments are restricted alphabets.
        if not all(re.fullmatch(r'[A-Za-z0-9_:*.-]+', str(v)) for v in arguments):
            raise ValueError('Restricted Redis fixture command required')
        command = ('AUTH ' + self.credentials['redis_password'] + '\nSELECT 1\n' +
                   ' '.join(map(str, arguments)) + '\n').encode('ascii')
        raw = run(['docker', 'exec', '-i', self.containers['redis'], 'redis-cli', '--raw'], command)
        lines = raw.decode('utf-8').splitlines()
        if len(lines) < 2 or lines[:2] != ['OK', 'OK']:
            raise RuntimeError('Owned Redis fixture authentication failed')
        return '\n'.join(lines[2:]).strip()

    def sql(self, query):
        if not query.lstrip().upper().startswith('SELECT ') or ';' in query:
            raise ValueError('Probe SQL is SELECT-only')
        raw = run(['docker', 'exec', '-i', self.containers['db'], 'mysql',
                   '--defaults-extra-file=/run/secrets/mysql-client.cnf',
                   '--batch', '--raw', '--skip-column-names', '--default-character-set=utf8mb4',
                   'teachingopen_dev'], (query + ';\n').encode('utf-8'))
        return raw.decode('utf-8').strip()

    def login(self, actor):
        if actor not in ACTORS:
            raise ValueError('Only five synthetic fixtures allowed')
        nonce = 'fixture-release-' + secrets.token_hex(8)
        response = self.api('GET', '/sys/randomImage/' + nonce)
        if not successful(response):
            raise RuntimeError('Fixture CAPTCHA generation failed')
        code = None
        for key in self.redis('KEYS', '*').splitlines():
            if not re.fullmatch('[a-fA-F0-9]{32}', key):
                continue
            try:
                value = json.loads(self.redis('GET', key))
            except ValueError:
                continue
            if isinstance(value, str) and hashlib.md5((value + nonce).encode()).hexdigest().lower() == key.lower():
                code = value
                break
        if code is None:
            raise RuntimeError('Owned fixture CAPTCHA unavailable')
        response = self.api('POST', '/sys/login', data={
            'username': 'fixture_' + actor, 'password': self.credentials['test_user_password'],
            'captcha': code, 'checkKey': nonce})
        if not successful(response):
            raise RuntimeError('Synthetic API fixture login failed')
        self.tokens[actor] = response[1]['result']['token']
        header = next((c for c in response[2].get_all('Set-Cookie', []) if c.startswith('teaching_media')), '')
        self.cookie_headers[actor] = header
        self.cookies[actor] = header.split(';')[0]
        return response


def successful(response):
    return response[0] == 200 and isinstance(response[1], dict) and response[1].get('success') is True


def denied(response):
    body = response[1]
    return ((response[0] in (401, 403, 404)) or
            (response[0] == 200 and isinstance(body, dict) and body.get('success') is False and
             body.get('code') in (401, 403, 404, 510)))


def paths(value):
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('path', 'url') and isinstance(item, str):
                result.add(item)
            result.update(paths(item))
    elif isinstance(value, list):
        for item in value:
            result.update(paths(item))
    return result


class AssetReferences(HTMLParser):
    """Accept normal HTML, including the build's unquoted minified attributes."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        reference = attributes.get('src') if tag == 'script' else attributes.get('href') if tag == 'link' else None
        if reference:
            parsed = urlsplit(reference)
            if not parsed.scheme and not parsed.netloc and re.search(r'\.(?:js|css)$', parsed.path):
                self.references.append(parsed.path)


class WebSocket:
    def __init__(self, user):
        self.sock = socket.create_connection(('127.0.0.1', 18190), timeout=5)
        self.closed = False
        key = base64.b64encode(os.urandom(16)).decode()
        request = ('GET /api/websocket/' + quote(user, safe='') + ' HTTP/1.1\r\n'
                   'Host: 127.0.0.1:18190\r\nOrigin: http://127.0.0.1:18190\r\n'
                   'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                   'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\n\r\n')
        self.sock.sendall(request.encode())
        header = b''
        while not header.endswith(b'\r\n\r\n') and len(header) < 16384:
            header += self.exact(1)
        fields = {k.lower(): v.strip() for k, v in
                  (line.split(b':', 1) for line in header.split(b'\r\n')[1:] if b':' in line)}
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not header.startswith(b'HTTP/1.1 101') or fields.get(b'sec-websocket-accept') != expected:
            self.sock.close()
            raise RuntimeError('Actual WebSocket upgrade failed')

    def exact(self, count):
        value = b''
        while len(value) < count:
            part = self.sock.recv(count - len(value))
            if not part:
                raise EOFError('WebSocket closed')
            value += part
        return value

    def send(self, value, opcode=1):
        value = value if isinstance(value, bytes) else json.dumps(value).encode()
        if len(value) > 16384:
            raise ValueError('Small probe frames only')
        mask = os.urandom(4)
        length = bytes([0x80 | len(value)]) if len(value) < 126 else bytes([0x80 | 126]) + struct.pack('!H', len(value))
        self.sock.sendall(bytes([0x80 | opcode]) + length + mask +
                          bytes(v ^ mask[i % 4] for i, v in enumerate(value)))

    def receive(self):
        self.sock.settimeout(5)
        first, second = self.exact(2)
        count = second & 0x7f
        if count == 126:
            count = struct.unpack('!H', self.exact(2))[0]
        if second & 0x80 or count == 127 or count > 16384 or not first & 0x80:
            raise ValueError('Unexpected server frame')
        value = self.exact(count)
        if first & 0xf == 8:
            self.closed = True
            return {'close': struct.unpack('!H', value[:2])[0] if len(value) >= 2 else 1005}
        if first & 0xf != 1:
            return {}
        return json.loads(value)

    def close(self):
        try:
            if not self.closed:
                self.send(struct.pack('!H', 1000), opcode=8)
        except OSError:
            pass
        finally:
            self.sock.close()


class Probe:
    def __init__(self, args):
        self.args = args
        self.bundle = args.bundle.absolute()
        self.phase = 'initialization'
        self.report = {
            'format': 1, 'observed_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'Fresh owned Linux containers; actual loopback HTTP, API fixture login, bounded SQL reads and WebSocket authentication. No browser, manual acceptance, production, deployment or capacity claim.',
            'fixture_login': 'CAPTCHA from owned Redis for synthetic API fixtures only',
            'data_retention': 'Normal API DELETE checks probe course/unit. Synthetic Python draft/upload and any rows remaining after failures are retained only in owned private bundle data for evidence. Root stops containers afterward.',
            'cases': [{'case': case, 'passed': False, 'status': 'not_run'} for case in CASES],
            'exceptions': [],
        }
        self.by_name = {c['case']: c for c in self.report['cases']}
        self.api_client = None

    def check(self, name, passed, response=None):
        case = self.by_name[name]
        case.update(passed=bool(passed), status='pass' if passed else 'fail', phase=self.phase)
        if response is not None:
            case.update(http_status=response[0], body_sha256=sha(response[3]))
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        return bool(passed)

    def group(self, phase, callback):
        self.phase = phase
        try:
            callback()
        except Exception as error:
            self.report['exceptions'].append({'phase': phase, 'exception_class': type(error).__name__})
            print('ERROR ' + phase + ' (' + type(error).__name__ + ')', flush=True)

    def preflight(self):
        self.phase = 'bundle_verification'
        self.bundle = self.bundle.resolve(strict=True)
        manifest_path = self.bundle / 'manifest.json'
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        tool = self.args.release_tool.resolve(strict=True)
        if sha(tool.read_bytes()) != manifest['generator_sha256']:
            raise ValueError('Frozen release tool mismatch')
        run([sys.executable, str(tool), 'verify', '--bundle', str(self.bundle)], timeout=60)
        if manifest_path.read_bytes() != manifest_raw:
            raise ValueError('Manifest changed during verification')
        self.manifest = manifest
        self.report['fingerprints'] = {
            'manifest_sha256': sha(manifest_raw), 'generator_sha256': manifest['generator_sha256'],
            'source_commit': manifest['source_commit'], 'artifact_inputs': manifest['artifact_inputs'],
        }
        self.check('frozen_bundle_verified', True)

        self.phase = 'container_boundary'
        compose = json.loads((self.bundle / 'compose.json').read_text())
        project = manifest['compose_project']
        if compose.get('name') != project or not re.fullmatch('teaching-candidate-[0-9a-f]{12}', project):
            raise ValueError('Frozen project identity mismatch')
        ids = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project]).decode().split()
        inspected = json.loads(run(['docker', 'inspect', *ids])) if ids else []
        containers = {}
        valid = len(inspected) == 4
        for container in inspected:
            labels = container['Config'].get('Labels') or {}
            service = labels.get('com.docker.compose.service')
            valid = valid and labels.get('com.docker.compose.project') == project and service in ('db', 'redis', 'api', 'web')
            valid = valid and labels.get('com.docker.compose.oneoff', 'False').lower() == 'false'
            valid = valid and container['State']['Running'] and service not in containers
            containers[service] = container
        valid = valid and set(containers) == {'db', 'redis', 'api', 'web'}
        self.check('four_owned_running_containers', valid)

        network_names = {kind: project + '_' + kind for kind in ('candidate', 'ingress')}
        inspected_networks = json.loads(run(['docker', 'network', 'inspect', *network_names.values()]))
        networks = {network['Name']: network for network in inspected_networks}
        expected_members = {
            'candidate': {c['Id'] for c in containers.values()},
            'ingress': {containers['web']['Id']},
        }
        network_ok = len(inspected_networks) == 2 and set(networks) == set(network_names.values())
        for kind, name in network_names.items():
            network = networks[name]
            labels = network.get('Labels') or {}
            network_ok = (network_ok and network['Internal'] is (kind == 'candidate') and
                          labels.get('com.docker.compose.project') == project and
                          labels.get('com.docker.compose.network') == kind and
                          set(network.get('Containers') or {}) == expected_members[kind])
        for service, container in containers.items():
            attached = container['NetworkSettings']['Networks']
            expected_names = set(network_names.values()) if service == 'web' else {network_names['candidate']}
            network_ok = (network_ok and set(attached) == expected_names and
                          all(attached[name]['NetworkID'] == networks[name]['Id'] for name in expected_names))
        self.check('owned_dual_network_isolation', network_ok)

        published, actual_published = [], []
        for service, container in containers.items():
            for port, bindings in (container['HostConfig'].get('PortBindings') or {}).items():
                for binding in bindings or []:
                    published.append((service, port, binding['HostIp'], binding['HostPort']))
            for port, bindings in (container['NetworkSettings'].get('Ports') or {}).items():
                for binding in bindings or []:
                    actual_published.append((service, port, binding['HostIp'], binding['HostPort']))
        expected_published = [('web', '80/tcp', '127.0.0.1', '18190')]
        port_ok = (published == expected_published and actual_published == expected_published and
                   not any(c['HostConfig'].get('PublishAllPorts') for c in containers.values()) and
                   manifest['port'] == 18190)
        self.check('only_web_loopback_18190_published', port_ok)

        mounts_ok = True
        for service, container in containers.items():
            expected = set()
            for volume in compose['services'][service].get('volumes', []):
                if not isinstance(volume, dict) or volume.get('type') != 'bind':
                    raise ValueError('Explicit bundle bind-mount contract required')
                source = Path(volume['source'])
                source = source if source.is_absolute() else self.bundle / source
                source = source.resolve(strict=True)
                if not source.is_relative_to(self.bundle):
                    raise ValueError('Container bind outside owned bundle')
                expected.add((str(source), volume['target'], not volume.get('read_only', False)))
            actual = {(m['Source'], m['Destination'], m['RW']) for m in container['Mounts'] if m['Type'] == 'bind'}
            mounts_ok = mounts_ok and expected == actual
            mounts_ok = mounts_ok and all(m['Type'] in ('bind', 'tmpfs') for m in container['Mounts'])
        mounts_ok = mounts_ok and (str(self.bundle / 'app/app.jar'), '/app/app.jar', False) in {
            (m['Source'], m['Destination'], m['RW']) for m in containers['api']['Mounts']}
        mounts_ok = mounts_ok and (str(self.bundle / 'web/dist'), '/usr/share/nginx/html', False) in {
            (m['Source'], m['Destination'], m['RW']) for m in containers['web']['Mounts']}
        self.check('exact_bundle_bind_mounts_with_readonly_jar_dist', mounts_ok)

        images_ok = manifest['platform'] == 'linux/arm64'
        for service, container in containers.items():
            image_ref = manifest['images'][service]
            if isinstance(image_ref, dict):
                image_ref = image_ref['reference']
            images_ok = images_ok and bool(re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', image_ref))
            resolved = json.loads(run(['docker', 'image', 'inspect', image_ref]))[0]
            images_ok = images_ok and container['Config']['Image'] == image_ref and container['Image'] == resolved['Id']
            images_ok = images_ok and resolved['Os'] == 'linux' and resolved['Architecture'] == 'arm64'
        self.check('pinned_linux_images_match_containers', images_ok)
        if not all((valid, network_ok, port_ok, mounts_ok, images_ok)):
            raise ValueError('Container boundary failed; refusing fixture traffic')
        if manifest['fixtures']['database'] != 'teachingopen_dev':
            raise ValueError('Frozen synthetic database name mismatch')
        credentials = private_json(self.bundle / 'config/credentials.json')
        if set(credentials) != {'mysql_root_password', 'mysql_app_password', 'redis_password', 'test_user_password'} or not all(
                isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value) for value in credentials.values()):
            raise ValueError('Unexpected fresh fixture credentials')
        self.api_client = Api(credentials, {s: c['Id'] for s, c in containers.items()})
        if self.api_client.sql("SELECT COUNT(*) FROM sys_user WHERE username NOT IN ('fixture_admin','fixture_teacher_a','fixture_teacher_b','fixture_student_a','fixture_student_b')") != '0':
            raise ValueError('Only synthetic accounts permitted')

    def static_and_auth(self):
        api = self.api_client
        response = api.api('GET', '/actuator/health')
        self.check('actual_health_up', response[0] == 200 and (response[1] or {}).get('status') == 'UP', response)
        index = (self.bundle / 'web/dist/index.html').read_bytes()
        response = api.http('GET', '/index.html')
        self.check('index_matches_frozen_body', response[0] == 200 and sha(response[3]) == sha(index), response)
        parser = AssetReferences()
        parser.feed(index.decode('utf-8'))
        assets = []
        for reference in parser.references:
            relative = reference.lstrip('/')
            path = self.bundle / 'web/dist' / relative
            if path.is_file() and path.resolve().is_relative_to(self.bundle / 'web/dist'):
                assets.append((path.stat().st_size, relative, path))
        if not assets:
            raise ValueError('No frozen referenced JS/CSS asset found')
        _, relative, path = min(assets)
        response = api.http('GET', '/' + quote(relative, safe='/'))
        self.check('referenced_asset_matches_frozen_body', response[0] == 200 and sha(response[3]) == sha(path.read_bytes()), response)
        response = api.api('GET', '/teaching/teachingCourse/getHomeCourse?pageSize=20')
        records = ((response[1] or {}).get('result') or {}).get('records', [])
        self.check('anonymous_home_courses', successful(response) and {'fixture_course_a', 'fixture_course_b', 'fixture_ui_course'}.issubset({r['id'] for r in records}), response)
        response = api.api('GET', '/sys/permission/getUserPermissionByToken', token='fixture-invalid-release-token')
        self.check('invalid_api_token_401', response[0] == 401 and (response[1] or {}).get('success') is False, response)

    def login_menu(self, actor):
        api = self.api_client
        api.login(actor)
        response = api.api('GET', '/sys/permission/getUserPermissionByToken', actor)
        granted = paths(((response[1] or {}).get('result') or {}).get('menu', []))
        role = 'admin' if actor == 'admin' else actor.split('_')[0]
        required = {'admin': '/course/course', 'teacher': '/teaching/workList', 'student': '/center/myAdditionalWork'}[role]
        permitted = required in granted and (role == 'admin' or '/course/course' not in granted)
        if role == 'student':
            permitted = permitted and '/teaching/workList' not in granted
        self.check('fixture_login_and_role_menu_' + actor, successful(response) and permitted, response)

    def course_access(self):
        api = self.api_client
        response = api.api('GET', '/teaching/teachingCourse/queryById?id=fixture_course_a', 'student_a')
        self.check('student_same_class_course_read', successful(response) and (response[1]['result'] or {}).get('id') == 'fixture_course_a', response)
        response = api.api('GET', '/teaching/teachingCourse/queryById?id=fixture_course_b', 'student_a')
        self.check('student_foreign_class_course_denied', denied(response) and not (response[1] or {}).get('result'), response)

    def management(self):
        api = self.api_client
        course, unit = 'fixture_release_probe_course', 'fixture_release_probe_unit'
        cbase, ubase = '/teaching/teachingCourse', '/teaching/teachingCourseUnit'
        for table, ident in (('teaching_course', course), ('teaching_course_unit', unit)):
            if api.sql('SELECT COUNT(*) FROM ' + table + ' WHERE id=' + literal(ident)) != '0':
                raise ValueError('Existing probe record; fresh bundle required')
        response = api.api('POST', cbase + '/add', 'admin', {'id': course, 'courseName': 'synthetic release course', 'showHome': 0, 'isShared': 0, 'departIds': 'fixture_school', 'delFlag': 0})
        self.check('admin_post_course_persisted', successful(response) and api.sql('SELECT course_name FROM teaching_course WHERE id=' + literal(course) + ' AND del_flag=0') == 'synthetic release course', response)
        response = api.api('POST', ubase + '/add', 'admin', {'id': unit, 'courseId': course, 'unitName': 'synthetic release unit', 'delFlag': 0})
        self.check('admin_post_unit_persisted', successful(response) and api.sql('SELECT unit_name FROM teaching_course_unit WHERE id=' + literal(unit) + ' AND del_flag=0') == 'synthetic release unit', response)
        response = api.api('PUT', cbase + '/edit', 'admin', {'id': course, 'courseName': 'synthetic release course edited'})
        self.check('admin_put_course_success', successful(response), response)
        response = api.api('PUT', ubase + '/edit', 'admin', {'id': unit, 'unitName': 'synthetic release unit edited'})
        self.check('admin_put_unit_success', successful(response), response)
        response = api.api('GET', cbase + '/queryById?id=' + course, 'admin')
        self.check('edited_course_api_and_db_reread', successful(response) and (response[1]['result'] or {}).get('courseName') == 'synthetic release course edited' and api.sql('SELECT course_name FROM teaching_course WHERE id=' + literal(course)) == 'synthetic release course edited', response)
        response = api.api('GET', ubase + '/queryById?id=' + unit, 'admin')
        self.check('edited_unit_api_and_db_reread', successful(response) and (response[1]['result'] or {}).get('unitName') == 'synthetic release unit edited' and api.sql('SELECT unit_name FROM teaching_course_unit WHERE id=' + literal(unit)) == 'synthetic release unit edited', response)
        course_reply = api.api('PUT', cbase + '/edit', 'student_a', {'id': course, 'courseName': 'synthetic forbidden course'})
        unit_reply = api.api('PUT', ubase + '/edit', 'student_a', {'id': unit, 'unitName': 'synthetic forbidden unit'})
        unchanged = (api.sql('SELECT course_name FROM teaching_course WHERE id=' + literal(course)) == 'synthetic release course edited' and
                     api.sql('SELECT unit_name FROM teaching_course_unit WHERE id=' + literal(unit)) == 'synthetic release unit edited')
        self.check('student_put_denied_and_both_values_unchanged', denied(course_reply) and denied(unit_reply) and unchanged, unit_reply)
        response = api.api('DELETE', ubase + '/delete?id=' + unit, 'admin')
        self.check('admin_delete_unit_persisted', successful(response) and api.sql('SELECT COUNT(*) FROM teaching_course_unit WHERE id=' + literal(unit) + ' AND del_flag=0') == '0', response)
        response = api.api('DELETE', cbase + '/delete?id=' + course, 'admin')
        self.check('admin_delete_course_persisted', successful(response) and api.sql('SELECT COUNT(*) FROM teaching_course WHERE id=' + literal(course) + ' AND del_flag=0') == '0', response)

    def media(self):
        api = self.api_client
        fixtures = self.manifest['fixtures']
        for kind, actor, extension, names in (
                ('public', None, '.png', ('anonymous_public_cover_get_bytes_nosniff', 'anonymous_public_cover_head_size_nosniff', 'anonymous_public_cover_range_original_bytes')),
                ('private', 'student_a', '.mp4', ('student_private_video_get_bytes_nosniff', 'student_private_video_head_size_nosniff', 'student_private_video_range_original_bytes'))):
            key = fixtures[kind + '_media_key']
            if not key.startswith('role-flow/') or not key.endswith(extension) or '..' in key.split('/'):
                raise ValueError('Synthetic media contract mismatch')
            expected_path = self.bundle / 'data/uploads' / key
            if not expected_path.resolve(strict=True).is_relative_to(self.bundle / 'data/uploads') or any(
                    p.is_symlink() for p in (expected_path, *expected_path.parents) if p.is_relative_to(self.bundle)):
                raise ValueError('Synthetic media must be ordinary owned files')
            expected = expected_path.read_bytes()
            if sha(expected) != fixtures[kind + '_media_sha256'] or len(expected) != fixtures[kind + '_media_bytes']:
                raise ValueError('Fixture media differs from frozen bytes')
            path = '/sys/common/static/' + quote(key, safe='/')
            response = api.api('GET', path, actor)
            self.check(names[0], response[0] == 200 and response[3] == expected and response[2].get('X-Content-Type-Options') == 'nosniff', response)
            response = api.api('HEAD', path, actor)
            self.check(names[1], response[0] == 200 and not response[3] and response[2].get('Content-Length') == str(len(expected)) and response[2].get('X-Content-Type-Options') == 'nosniff', response)
            response = api.api('GET', path, actor, headers={'Range': 'bytes=3-19'})
            self.check(names[2], response[0] == 206 and response[3] == expected[3:20] and response[2].get('Content-Range') == 'bytes 3-19/' + str(len(expected)) and response[2].get('X-Content-Type-Options') == 'nosniff', response)
        response = api.api('GET', '/sys/common/static/' + quote(fixtures['private_media_key'], safe='/'), 'student_b', headers={'Range': 'bytes=0-19'})
        self.check('foreign_private_video_denied', response[0] == 403 and 'Content-Range' not in response[2], response)

    def python_draft(self):
        api = self.api_client
        name = 'synthetic-python-release-probe'
        if api.sql('SELECT COUNT(*) FROM teaching_work WHERE work_name=' + literal(name)) != '0':
            raise ValueError('Existing synthetic Python probe; fresh bundle required')
        payload = '# 合成容器候选探针\nprint("synthetic release probe")\n'.encode('utf-8')
        boundary = 'fixture-release-' + secrets.token_hex(12)
        directory, filename = 'fixture-release-probe/中文上传', '合成探针.py'
        multipart = ('--' + boundary + '\r\nContent-Disposition: form-data; name="bizPath"\r\n\r\n' + directory +
                     '\r\n--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="' + filename +
                     '"\r\nContent-Type: text/x-python\r\n\r\n').encode('utf-8') + payload + ('\r\n--' + boundary + '--\r\n').encode()
        response = api.api('POST', '/sys/common/upload', 'student_a', multipart,
                           headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        key = (response[1] or {}).get('message', '')
        safe = isinstance(key, str) and key.startswith(directory + '/') and '..' not in key.split('/') and key.endswith('.py')
        if not self.check('student_real_multipart_python_upload', successful(response) and safe, response):
            return
        response = api.api('POST', '/system/sysFile/add', 'student_a', {'fileName': filename, 'filePath': key, 'fileLocation': 1, 'fileType': 2, 'fileTag': 'synthetic-python'})
        registered = (response[1] or {}).get('result') or {}
        file_id = registered.get('id')
        valid_id = isinstance(file_id, str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', file_id)
        sql = ('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(file_id or '') +
               ' AND BINARY file_path=BINARY ' + literal(key) + " AND create_by='fixture_student_a' AND file_location=1 AND del_flag=0")
        if not self.check('student_file_registration_and_db_owner', successful(response) and valid_id and registered.get('filePath') == key and api.sql(sql) == '1', response):
            return
        response = api.api('POST', '/teaching/teachingWork/submit', 'student_a', {'workName': name, 'workType': '4', 'workStatus': '0', 'workFile': file_id, 'workCover': ''})
        work = (response[1] or {}).get('result') or {}
        work_id = work.get('id')
        if not self.check('student_personal_python_draft_submit', successful(response) and isinstance(work_id, str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', work_id) and str(work.get('workStatus')) == '0' and str(work.get('workType')) == '4', response):
            return
        sql = ('SELECT COUNT(*) FROM teaching_work WHERE id=' + literal(work_id) + " AND user_id='fixture_student_a' AND create_by='fixture_student_a' AND work_type='4' AND work_status=0 AND del_flag=0 AND work_scene='create' AND COALESCE(depart_id,'')='' AND COALESCE(course_id,'')='' AND COALESCE(additional_id,'')='' AND work_file=" + literal(file_id))
        self.check('python_draft_db_identity_status_persisted', api.sql(sql) == '1')
        response = api.api('GET', '/teaching/teachingWork/studentWorkInfo?workId=' + quote(work_id, safe=''), 'student_a')
        reread = (response[1] or {}).get('result') or {}
        self.check('student_python_draft_reopens', successful(response) and reread.get('id') == work_id and reread.get('workFile') == file_id and str(reread.get('workType')) == '4' and str(reread.get('workStatus')) == '0', response)
        path = '/sys/common/static/' + quote(key, safe='/')
        response = api.api('GET', path, 'student_a')
        self.check('python_attachment_download_full_hash', response[0] == 200 and sha(response[3]) == sha(payload) and response[2].get('X-Content-Type-Options') == 'nosniff', response)
        work_reply = api.api('GET', '/teaching/teachingWork/studentWorkInfo?workId=' + quote(work_id, safe=''), 'student_b')
        file_reply = api.api('GET', path, 'student_b')
        self.check('foreign_python_draft_and_download_denied', denied(work_reply) and not (work_reply[1] or {}).get('result') and file_reply[0] == 403 and sha(file_reply[3]) != sha(payload), file_reply)

    def cookie_and_socket(self):
        api = self.api_client
        header, pair = api.cookie_headers['student_a'], api.cookies['student_a']
        attrs = ('HttpOnly' in header and 'SameSite=Strict' in header and
                 'Path=/api/sys/common/static' in header and 'Domain=' not in header and bool(pair))
        path = '/sys/common/static/' + quote(self.manifest['fixtures']['private_media_key'], safe='/')
        response = api.api('GET', path, headers={'Cookie': pair})
        expected_hash = self.manifest['fixtures']['private_media_sha256']
        self.check('media_cookie_httponly_path_samesite_and_media_read', attrs and response[0] == 200 and sha(response[3]) == expected_hash, response)
        response = api.api('GET', '/sys/permission/getUserPermissionByToken', headers={'Cookie': pair})
        self.check('media_cookie_cannot_authorize_api', response[0] == 401, response)

        ws = WebSocket('fixture_student_a')
        try:
            ws.send({'type': 'authenticate', 'token': api.tokens['student_a']})
            self.check('actual_websocket_upgrade_and_authentication_reply', (ws.receive() or {}).get('cmd') == 'authenticated')
        finally:
            ws.close()
        token = api.tokens['student_a']
        logout = api.api('GET', '/sys/logout', 'student_a')
        media = api.api('GET', path, headers={'Cookie': pair})
        normal = api.api('GET', '/sys/permission/getUserPermissionByToken', token=token)
        self.check('logout_revokes_token_and_media_cookie', successful(logout) and media[0] == 401 and normal[0] == 401, media)
        api.tokens.pop('student_a', None)

    def execute(self):
        try:
            self.preflight()
        except Exception as error:
            self.report['exceptions'].append({'phase': self.phase, 'exception_class': type(error).__name__})
            print('ERROR ' + self.phase + ' (' + type(error).__name__ + ')', flush=True)
            return
        self.group('static_and_anonymous_api', self.static_and_auth)
        for actor in ACTORS:
            self.group('fixture_login_' + actor, lambda actor=actor: self.login_menu(actor))
        self.group('class_course_authorization', self.course_access)
        self.group('course_and_unit_business_methods', self.management)
        self.group('public_and_private_media', self.media)
        self.group('python_upload_personal_draft', self.python_draft)
        self.group('media_cookie_revocation_and_websocket', self.cookie_and_socket)

    def finish(self):
        if self.api_client is not None:
            self.phase = 'fixture_logout_finally'
            for actor in list(self.api_client.tokens):
                try:
                    self.api_client.api('GET', '/sys/logout', actor)
                except Exception as error:
                    self.report['exceptions'].append({'phase': self.phase + '_' + actor, 'exception_class': type(error).__name__})
            self.api_client.tokens.clear()
            self.api_client.cookies.clear()
            self.api_client.credentials.clear()
        cases = self.report['cases']
        self.report.update(passed=sum(c['passed'] for c in cases), total=len(cases),
                           failed=sum(c['status'] == 'fail' for c in cases),
                           not_run=sum(c['status'] == 'not_run' for c in cases))
        self.report['all_passed'] = self.report['passed'] == self.report['total'] and not self.report['exceptions']
        fd = os.open(self.args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(self.report, output, ensure_ascii=False, indent=2)
            output.write('\n')
        print(json.dumps({k: self.report[k] for k in ('passed', 'total', 'failed', 'not_run', 'all_passed')}) + '\nPrivate report saved.', flush=True)
        return self.report['all_passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--release-tool', type=Path, default=Path(__file__).with_name('candidate_release.py'),
                        help='Explicit frozen tool path; must match manifest.generator_sha256')
    args = parser.parse_args()
    try:
        args.output = prepare_output(args.output)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    probe = None
    try:
        probe = Probe(args)
        probe.execute()
    finally:
        if probe is not None:
            success = probe.finish()
    return 0 if probe is not None and success else 1


if __name__ == '__main__':
    raise SystemExit(main())
