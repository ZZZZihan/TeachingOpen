#!/usr/bin/env python3
"""Check the public-resource/upload boundary in one owned synthetic runtime.

Uses the same secure assertions for old and new frozen JARs. Login uses the
existing FixtureApi helper and the isolated Redis CAPTCHA; it is API evidence,
not a browser login or production acceptance test.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4
from zipfile import ZipFile

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write
from local_runtime import assert_app_config, assert_database, load_ports, mysql_command

WORKSPACE = Path('/Users/xuzihan/Documents/Projects/TeachingOpen')
RUNTIME = WORKSPACE / '.devspace/resource-route-1005'
PORTS = {'mysql': 13374, 'redis': 16447, 'backend': 18184, 'frontend': 18185}
ACTORS = ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise RuntimeError('Local resource probe refuses redirects')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def literal(value):
    return "''" if str(value) == '' else 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def sql(runtime, query):
    command = mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', query]
    result = subprocess.run(command, capture_output=True, text=True, timeout=25)
    if result.returncode:
        private_write(runtime / 'logs' / ('resource-sql-' + uuid4().hex[:10] + '.log'), result.stderr)
        raise RuntimeError('Owned synthetic SQL failed; inspect private runtime log')
    return result.stdout.rstrip('\n')


def snapshot_users(runtime):
    columns = [row.split('\t')[0] for row in sql(runtime, 'SHOW COLUMNS FROM sys_user').splitlines()]
    if any(not column.replace('_', '').isalnum() for column in columns):
        raise ValueError('Unexpected synthetic user schema')
    expression = ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'~')" for column in columns)
    rows = [row.split('\t')[1:] for row in sql(runtime, "SELECT 'ROW'," + expression + ' FROM sys_user ORDER BY id').splitlines()]
    return columns, rows


def restore_users(runtime, saved):
    columns, rows = saved
    encode = lambda value: 'NULL' if value == '~' else "''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)'
    identity = columns.index('id')
    for row in rows:
        values = ['`' + col + '`=' + encode(value) for col, value in zip(columns, row) if col != 'id']
        sql(runtime, 'UPDATE sys_user SET ' + ','.join(values) + ' WHERE id=' + encode(row[identity]))


def guard(runtime, jar, expected_hash):
    if runtime != runtime.resolve() or runtime != RUNTIME or runtime.stat().st_mode & 0o077 or load_ports(runtime) != PORTS:
        raise ValueError('Only the owned resource-route-1005 runtime and fixed ports are accepted')
    if jar != jar.resolve() or not jar.is_file() or digest(jar.read_bytes()) != expected_hash:
        raise ValueError('Frozen candidate JAR does not match its expected SHA-256')
    assert_app_config(runtime)
    assert_database(runtime)
    config = runtime / 'config/application-localtest.properties'
    props = dict(line.split('=', 1) for line in config.read_text().splitlines() if line and not line.startswith('#') and '=' in line)
    if props.get('jeecg.path.webapp') != str(runtime / 'webapp') or props.get('spring.redis.database') != '1' or props.get('jeecg.path.staticDomain') != '/api/sys/common/static':
        raise ValueError('Public resources or Redis escaped the owned runtime')
    expected_users = '\n'.join('fixture_' + actor for actor in sorted(ACTORS))
    if sql(runtime, 'SELECT id FROM sys_user ORDER BY id') != expected_users or sql(runtime, 'SELECT username FROM sys_user ORDER BY username') != expected_users:
        raise ValueError('Expected exactly the five synthetic fixture identities')
    process = json.loads((runtime / 'backend-process.json').read_text())
    command = subprocess.check_output(['ps', '-p', str(process['pid']), '-o', 'command='], text=True)
    config_arg = '--spring.config.additional-location=file:' + str(runtime / 'config') + '/'
    if config_arg not in command or '--spring.profiles.active=dev,localtest' not in command or str(jar) not in command:
        raise ValueError('Backend process configuration does not match the owned runtime')
    for service, pid_path in (('mysql', 'mysql.pid'), ('redis', 'redis.pid'), ('backend', 'backend.pid')):
        pid = int((runtime / pid_path).read_text())
        result = subprocess.run(['lsof', '-nP', '-iTCP:' + str(PORTS[service]), '-sTCP:LISTEN', '-FpFn'], capture_output=True, text=True)
        listeners = {int(line[1:]) for line in result.stdout.splitlines() if line.startswith('p')}
        names = [line[1:] for line in result.stdout.splitlines() if line.startswith('n')]
        if result.returncode or listeners != {pid} or names != ['127.0.0.1:' + str(PORTS[service])]:
            raise ValueError('Listener ownership or loopback binding does not match ' + service)
    if (runtime / 'tools').resolve() != WORKSPACE / '.devspace/backend-runtime/tools':
        raise ValueError('Runtime does not use the fixed local toolchain')
    return {'runtime': runtime.name, 'ports': PORTS, 'jar_sha256': expected_hash,
            'configuration_sha256': digest(config.read_bytes()), 'ports_sha256': digest((runtime / 'ports.json').read_bytes()),
            'backend_pid': process['pid'], 'loopback_listener_ownership_checked': True,
            'fixture_identity_set_checked': True}


def verify(args):
    runtime, jar = args.runtime.absolute(), args.jar.absolute()
    evidence_root = WORKSPACE / '.devspace/artifacts/upload-resource-boundary'
    output = args.output.absolute()
    if output != output.resolve() or not any(root in output.parents for root in (runtime, evidence_root)):
        raise ValueError('Write evidence only inside the owned runtime or private resource-boundary artifacts')
    if args.output.exists():
        raise ValueError('Preserve previous evidence; choose a new output path')
    report = {'scope': 'Actual local HTTP and MySQL with five synthetic accounts; no browser, production or human acceptance.',
              'observed_utc': datetime.now(timezone.utc).isoformat(), 'cases': [], 'guard': guard(runtime, jar, args.jar_sha256)}
    lock = runtime / 'resource-boundary-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    # Fixture IDs are VARCHAR(32); leave room for suffixes such as _file_0.
    prefix = 'rbnd_' + uuid4().hex[:10]
    owned_files, owned_dirs, records = [], [], []
    api = None
    before, attachments, webapp, saved_users = None, None, None, None
    # Resource requests go directly to loopback and never follow a redirect.
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def check(name, passed, reply=None, **detail):
        case = {'case': name, 'passed': bool(passed), **detail}
        if reply:
            status, body, headers = reply
            case.update(http_status=status, response_bytes=len(body), response_sha256=digest(body),
                        content_type=headers.get('Content-Type'), content_length=headers.get('Content-Length'),
                        content_range=headers.get('Content-Range'))
        report['cases'].append(case)
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    def create(root, key, payload):
        path = root / key
        if path.exists():
            raise ValueError('Refuse to overwrite an existing test path')
        parents = []
        parent = path.parent
        while parent != root and not parent.exists():
            parents.append(parent)
            parent = parent.parent
        for directory in reversed(parents):
            directory.mkdir(mode=0o700)
            owned_dirs.append(directory)
        private_write(path, payload)
        owned_files.append(path)

    def record(key):
        identity = prefix + '_file_' + str(len(records))
        work = prefix + '_work_' + str(len(records))
        sql(runtime, 'INSERT INTO sys_file (id,create_by,file_path,file_name,file_location,file_type) VALUES (' +
            ','.join(map(literal, (identity, 'fixture_student_a', key, 'owned resource canary'))) + ',1,2)')
        records.append((identity, work))
        sql(runtime, 'INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_file,work_type,work_status,create_by,create_time) VALUES (' +
            ','.join(map(literal, (work, 'fixture_student_a', 'fixture_class_a', 'owned resource canary', identity, '1'))) +
            ",0,'fixture_student_a','2026-10-05 00:00:00')")
        return work

    def request(route, actor, method):
        headers = {'Range': 'bytes=0-7'} if method == 'Range' else {}
        if actor:
            headers['X-Access-Token'] = api.tokens[actor]
        req = Request('http://127.0.0.1:' + str(PORTS['backend']) + '/api' + quote(route, safe='/'),
                      headers=headers, method='GET' if method == 'Range' else method)
        try:
            response = opener.open(req, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise RuntimeError('Local resource response exceeds the two MiB probe limit')
            return response.status, body, response.headers

    def allowed(reply, payload, method, canonical=False):
        status, body, headers = reply
        if method == 'HEAD':
            good = status == 200 and body == b'' and headers.get('Content-Length') == str(len(payload)) and 'Content-Range' not in headers
        elif method == 'Range':
            good = status == 206 and body == payload[:8] and headers.get('Content-Range') == 'bytes 0-7/' + str(len(payload)) and headers.get('Content-Length') == '8'
        else:
            good = status == 200 and body == payload
        return good and (not canonical or headers.get('Cache-Control') == 'no-store')

    def denied(reply, payload):
        status, body, headers = reply
        return status in (400, 401, 403, 404) and payload not in body and payload[:8] not in body and 'Content-Range' not in headers

    try:
        api = FixtureApi(runtime, jar)
        before, attachments, webapp = database_inventory(runtime), file_inventory(runtime / 'uploads'), file_inventory(runtime / 'webapp')
        saved_users = snapshot_users(runtime)
        if len(before) != 69 or len(saved_users[1]) != 5:
            raise ValueError('Expected 69 base tables and five synthetic users')
        private_write(runtime / 'config' / (prefix + '-before.json'), json.dumps({'database': before, 'uploads': attachments, 'webapp': webapp, 'users': saved_users}))
        for actor in ACTORS:
            api.login(actor)
        items = []
        for index, extension in enumerate(('png', 'html', 'pdf')):
            for nested in (False, True):
                key = (prefix + '/' if nested else '') + prefix + ('_nested.' if nested else '_root.') + extension
                payload = ('PRIVATE_' + str(index) + ('_nested_' if nested else '_root_') + prefix + '_0123456789').encode()
                create(runtime / 'uploads', key, payload)
                record(key)
                items.append((key, payload))
        for anon_prefix in ('generic', 'sys/common/pdf'):
            key = anon_prefix + '/' + prefix + '.txt'
            payload = ('PRIVATE_PREFIX_' + anon_prefix + '_' + prefix + '_0123456789').encode()
            create(runtime / 'uploads', key, payload)
            record(key)
            items.append((key, payload))
        for key, payload in items:
            label = key.replace(prefix, '<owned>')
            for actor in (None, 'student_a', 'student_b', 'teacher_a', 'teacher_b', 'admin'):
                for method in ('GET', 'HEAD', 'Range'):
                    reply = request('/sys/common/static/' + key, actor, method)
                    permitted = actor in ('student_a', 'teacher_a', 'admin')
                    check('canonical ' + label + ' ' + str(actor or 'anonymous') + ' ' + method,
                          allowed(reply, payload, method, canonical=True) if permitted else denied(reply, payload), reply,
                          expected='authorized upload bytes' if permitted else 'denied')
                    reply = request('/' + key, actor, method)
                    check('public route cannot expose upload ' + label + ' ' + str(actor or 'anonymous') + ' ' + method,
                          denied(reply, payload), reply, expected='denied')
            for alias in (key.upper(), key[:-3] + key[-3:].upper()):
                for route in ('/sys/common/static/', '/'):
                    for method in ('GET', 'HEAD', 'Range'):
                        reply = request(route + alias, 'student_a', method)
                        check('case alias cannot expose upload ' + route + label + ' ' + method,
                              denied(reply, payload), reply, expected='denied')
        # A published upload remains public through its canonical guarded route.
        public_upload_key, public_upload_bytes = items[0]
        sql(runtime, 'UPDATE teaching_work SET work_status=3 WHERE id=' + literal(records[0][1]))
        for method in ('GET', 'HEAD', 'Range'):
            reply = request('/sys/common/static/' + public_upload_key, None, method)
            check('published upload remains public on canonical route ' + method,
                  allowed(reply, public_upload_bytes, method, canonical=True), reply)
            reply = request('/' + public_upload_key, None, method)
            check('published upload has no public resource alias ' + method, denied(reply, public_upload_bytes), reply)
        # Public application assets, including a same-key collision with uploads.
        public_items = []
        for extension in ('png', 'html', 'pdf'):
            key = prefix + '_public.' + extension
            payload = ('PUBLIC_WEBAPP_' + extension + '_' + prefix + '_abcdefghij').encode()
            create(runtime / 'webapp', key, payload)
            public_items.append((key, payload))
        key = 'generic/' + prefix + '_public.txt'
        payload = ('PUBLIC_WEBAPP_GENERIC_' + prefix + '_abcdefghij').encode()
        create(runtime / 'webapp', key, payload)
        public_items.append((key, payload))
        collision_key, collision_private = items[1]
        collision_public = ('PUBLIC_WEBAPP_COLLISION_' + prefix + '_abcdefghij').encode()
        create(runtime / 'webapp', collision_key, collision_public)
        public_items.append((collision_key, collision_public))
        for key, payload in public_items:
            for actor in (None, 'student_a', 'student_b'):
                for method in ('GET', 'HEAD', 'Range'):
                    reply = request('/' + key, actor, method)
                    check('webapp asset retains exact public bytes ' + key.replace(prefix, '<owned>') + ' ' + str(actor or 'anonymous') + ' ' + method,
                          allowed(reply, payload, method), reply)
        for actor in (None, 'student_a', 'student_b'):
            for method in ('GET', 'HEAD', 'Range'):
                reply = request('/sys/common/static/' + collision_key, actor, method)
                check('collision canonical route keeps upload permissions ' + str(actor or 'anonymous') + ' ' + method,
                      allowed(reply, collision_private, method, canonical=True) if actor == 'student_a' else denied(reply, collision_private), reply)
        # Preserve actual packaged public resources as well as filesystem assets.
        with ZipFile(jar) as bundle:
            for key in ('generic/web/viewer.html', 'generic/web/viewer.css'):
                payload = bundle.read('BOOT-INF/classes/static/' + key)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise RuntimeError('Packaged public resource exceeds the probe limit')
                for method in ('GET', 'HEAD', 'Range'):
                    reply = request('/' + key, None, method)
                    check('packaged classpath asset retains exact bytes ' + key + ' ' + method,
                          allowed(reply, payload, method), reply,
                          expected_resource_sha256=digest(payload), expected_resource_bytes=len(payload))
        if args.download_regression:
            probe_path = Path(__file__).with_name('verify-local-download.py')
            spec = importlib.util.spec_from_file_location('download_boundary_regression', probe_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = runtime / (prefix + '-download-regression.json')
            ok = module.verify(argparse.Namespace(runtime=runtime, jar=jar, output=output, expect_legacy=False))
            regression = json.loads(output.read_text())
            report['canonical_download_regression'] = {'passed': regression['passed'], 'total': regression['total'], 'probe_sha256': digest(probe_path.read_bytes())}
            check('existing canonical download regression passes', ok and regression['passed'] == regression['total'])
    except Exception as error:
        report['infrastructure_error_type'] = type(error).__name__
        check('probe completed without infrastructure error', False)
    finally:
        if api:
            try:
                api.close()
            except Exception as error:
                report['logout_error_type'] = type(error).__name__
                check('synthetic logout cleanup succeeds', False)
        try:
            for identity, work in records:
                sql(runtime, 'DELETE FROM teaching_work WHERE id=' + literal(work))
                sql(runtime, 'DELETE FROM sys_file WHERE id=' + literal(identity))
            for path in reversed(owned_files):
                path.unlink(missing_ok=True)
            for directory in reversed(owned_dirs):
                directory.rmdir()
            if saved_users:
                restore_users(runtime, saved_users)
            if before:
                after = database_inventory(runtime)
                restoration = {'table_count': len(before), 'non_audit_table_count': len(before) - 1,
                               'same_table_set': before.keys() == after.keys(),
                               'changed_schemas': [t for t in before if before[t]['schema_sha256'] != after.get(t, {}).get('schema_sha256')],
                               'changed_non_audit_tables': [t for t in before if t != 'sys_log' and before[t] != after.get(t)],
                               'attachments_equal': attachments == file_inventory(runtime / 'uploads'),
                               'webapp_files_equal': webapp == file_inventory(runtime / 'webapp'),
                               'synthetic_user_columns_restored': saved_users == snapshot_users(runtime)}
                report['restoration'] = restoration
                check('69 schemas 68 non-audit tables users and all attachment/public files restored',
                      restoration['same_table_set'] and not restoration['changed_schemas'] and not restoration['changed_non_audit_tables']
                      and restoration['attachments_equal'] and restoration['webapp_files_equal'] and restoration['synthetic_user_columns_restored'])
                private_write(runtime / 'config' / (prefix + '-after.json'), json.dumps({'database': after, 'uploads': file_inventory(runtime / 'uploads'), 'webapp': file_inventory(runtime / 'webapp')}))
        except Exception as error:
            report['cleanup_error_type'] = type(error).__name__
            check('probe cleanup completed without infrastructure error', False)
        finally:
            lock.unlink()
    report.update(jar_sha256=args.jar_sha256, probe_sha256=digest(Path(__file__).read_bytes()),
                  total=len(report['cases']), passed=sum(c['passed'] for c in report['cases']))
    report['probe_tool_sha256'] = {name: digest(Path(__file__).with_name(name).read_bytes()) for name in
                                  ('local_http.py', 'local_recovery.py', 'local_runtime.py', 'run-backend.py',
                                   'prepare-local.py', 'seed-fixtures.py', 'verify-local-download.py')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ('passed', 'total', 'jar_sha256', 'restoration', 'infrastructure_error_type', 'cleanup_error_type')}))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--jar-sha256', required=True)
    parser.add_argument('--download-regression', action='store_true')
    raise SystemExit(verify(parser.parse_args()))
