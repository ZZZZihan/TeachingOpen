#!/usr/bin/env python3
"""Serve a real teaching SPA over the dedicated five-account synthetic runtime.

This task-specific tool never seeds assignments, submissions or feedback. Start
the selected backend separately, then run with --runtime --jar --dist --output.
SIGINT/SIGTERM closes the frontend and restores the selected tables and newly
uploaded files. After SIGKILL, run the same command with --restore; the same JAR
must still be running and the frontend port must be free. A failed restoration
keeps its private snapshot for investigation; it is never silently overwritten.
"""
import argparse
import base64
import contextlib
import fcntl
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from local_http import FixtureApi
from local_recovery import file_inventory, private_write, sha256, sql
from local_runtime import assert_app_config, assert_database, assert_mysql_owner, load_ports, mysql_command
from role_flow_fixture import (ACCOUNT_ROLES, DICT_ITEMS, ROUTES, compare_records,
                               complete_records, equivalent, ident,
                               normalized_type, base_records, schema_model)

HERE = Path(__file__).resolve().parent
EXPECTED_RUNTIME = Path('/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/media-index-1011')
EXPECTED_PORTS = {'mysql': 13391, 'redis': 16451, 'backend': 18191, 'frontend': 18192}
ACTORS = frozenset(('teacher_a', 'student_a', 'teacher_b', 'student_b'))
BACKUP_NAME = 'teaching-journey-backup'
KIND = 'teachingopen-synthetic-teaching-journey'
FORMAT = 1
PREFIX = 'fixture_journey_'
# Login updates sys_user.org_code. UI preparation updates the two synthetic
# class categories. The remaining tables are exactly the teaching journey's
# writes, media index derivatives, and normal menu/dictionary registrations.
TABLES = ('sys_user', 'sys_depart', 'sys_permission', 'sys_role_permission',
          'sys_dict', 'sys_dict_item', 'sys_file', 'sys_data_log', 'teaching_additional_work',
          'teaching_work', 'teaching_work_correct', 'teaching_work_comment',
          'teaching_depart_day_log', 'teaching_work_event', 'teaching_unit_view_event',
          'sys_local_file_reference', 'sys_local_file_reference_state')
ADDITIONAL_COLUMNS = {
    'teaching_registration_profile': [('user_id', 'varchar(32)', False, None),
        ('identity', 'varchar(16)', False, None), ('create_time', 'datetime', False, None)],
    'teaching_unit_view_event': [('depart_id', 'varchar(64)', False, None),
        ('unit_id', 'varchar(64)', False, None), ('observed_user_id', 'varchar(64)', False, None),
        ('event_state', 'varchar(32)', False, None), ('counted_day', 'date', True, None),
        ('observed_at', 'timestamp', False, 'CURRENT_TIMESTAMP')],
    'teaching_work_event': [('work_id', 'varchar(64)', False, None),
        ('event_type', 'varchar(32)', False, None), ('depart_id', 'varchar(64)', False, None),
        ('event_state', 'varchar(32)', False, None), ('counted_day', 'date', True, None),
        ('observed_at', 'timestamp', False, 'CURRENT_TIMESTAMP')],
    'teaching_work_event_cutover': [('id', 'tinyint', False, None),
        ('completed_at', 'timestamp', False, 'CURRENT_TIMESTAMP')],
    'sys_local_file_reference': [('source_type', 'varchar(40)', False, None),
        ('source_id', 'varchar(64)', False, None), ('field_name', 'varchar(40)', False, None),
        ('reference_kind', 'varchar(8)', False, None), ('reference_hash', 'char(64)', False, None),
        ('reference_value', 'mediumtext', False, None)],
    'sys_local_file_reference_state': [('id', 'int', False, None),
        ('version', 'int', False, '0'), ('static_domain', 'varchar(512)', True, None)],
}
spec = importlib.util.spec_from_file_location('teaching_journey_frontend', HERE / 'serve-frontend.py')
frontend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                      separators=(',', ':')).encode()).hexdigest()


def private_file(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise RuntimeError('Expected a private ordinary fixture file')
    return path


def checked_path(path):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise RuntimeError('Symlink paths are not accepted')
    return path


@contextlib.contextmanager
def lock(runtime):
    path = runtime / 'config/teaching-journey.lock'
    if path.is_symlink():
        raise RuntimeError('Unsafe fixture lock')
    with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another teaching journey fixture operation is running')
        yield


def table_rows(runtime, table, columns):
    expression = ','.join("IFNULL(HEX(CAST(" + ident(name) + " AS BINARY)),'~')" for name in columns)
    lines = sql(runtime, "SELECT 'ROW'," + expression + ' FROM teachingopen_dev.' + ident(table)).splitlines()
    return sorted([[None if value == '~' else value for value in line.split('\t')[1:]]
                   for line in lines], key=lambda row: json.dumps(row))


def decoded(rows, columns):
    return [dict(zip(columns, [None if value is None else bytes.fromhex(value).decode()
                              for value in row])) for row in rows]


def reviewed_model():
    model = schema_model()
    for table, columns in ADDITIONAL_COLUMNS.items():
        model[table] = {name: {'type': kind, 'nullable': nullable, 'default': default}
                        for name, kind, nullable, default in columns}
    return model


def schema_guard(runtime):
    model, found = reviewed_model(), {}
    output = sql(runtime, "SELECT TABLE_NAME,HEX(COLUMN_NAME),HEX(COLUMN_TYPE),IS_NULLABLE,"
        "IFNULL(HEX(COLUMN_DEFAULT),'~') FROM information_schema.columns "
        "WHERE TABLE_SCHEMA='teachingopen_dev' ORDER BY TABLE_NAME,ORDINAL_POSITION")
    for line in output.splitlines():
        table, name, kind, nullable, default = line.split('\t')
        found.setdefault(table, {})[bytes.fromhex(name).decode()] = {
            'type': normalized_type(bytes.fromhex(kind).decode()), 'nullable': nullable == 'YES',
            'default': None if default == '~' else bytes.fromhex(default).decode()}
    if set(found) != set(model):
        raise RuntimeError('Expected exactly the reviewed 75-table synthetic schema')
    for table, columns in model.items():
        if list(found[table]) != list(columns):
            raise RuntimeError('Unreviewed synthetic columns: ' + table)
        for name, expected in columns.items():
            actual = found[table][name]
            if (actual['type'] != expected['type'] or actual['nullable'] != expected['nullable']
                    or not equivalent(actual['default'], expected['default'], expected)):
                raise RuntimeError('Unreviewed synthetic column metadata: ' + table)
    objects = sql(runtime, "SELECT (SELECT COUNT(*) FROM information_schema.tables "
        "WHERE TABLE_SCHEMA='teachingopen_dev' AND (TABLE_TYPE<>'BASE TABLE' OR ENGINE<>'InnoDB'))+"
        "(SELECT COUNT(*) FROM information_schema.triggers WHERE TRIGGER_SCHEMA='teachingopen_dev')+"
        "(SELECT COUNT(*) FROM information_schema.routines WHERE ROUTINE_SCHEMA='teachingopen_dev')+"
        "(SELECT COUNT(*) FROM information_schema.events WHERE EVENT_SCHEMA='teachingopen_dev')")
    if objects != '0':
        raise RuntimeError('Unreviewed synthetic objects or engines')
    return model


def runtime_guard(runtime, jar):
    runtime = checked_path(runtime)
    if runtime != EXPECTED_RUNTIME or not runtime.is_dir() or runtime.stat().st_mode & 0o077:
        raise RuntimeError('Only the private media-index-1011 synthetic runtime is supported')
    for name in ('config/credentials.json', 'config/mysql-admin-client.cnf',
                 'config/application-localtest.properties', 'config/fixture-seed.sql'):
        private_file(runtime / name)
    if load_ports(runtime) != EXPECTED_PORTS:
        raise RuntimeError('Dedicated synthetic ports changed')
    assert_mysql_owner(runtime)
    assert_app_config(runtime)
    assert_database(runtime)
    api = FixtureApi(runtime, checked_path(jar))
    expected_accounts = {name: {'id': name, 'role': role,
        'class_id': 'fixture_school' if role == 'admin' else 'fixture_class_' + name[-1]}
        for name, role in ACCOUNT_ROLES.items()}
    if json.loads((runtime / 'fixture-accounts.json').read_text()) != expected_accounts:
        raise RuntimeError('Account metadata escaped the five canonical synthetic actors')
    identity = sql(runtime, "SELECT CONCAT(id,'|',username,'|',status,'|',del_flag,'|',user_identity) "
                   'FROM teachingopen_dev.sys_user ORDER BY id').splitlines()
    expected = sorted(name + '|' + name + '|1|0|' + ('1' if role == 'student' else '2')
                      for name, role in ACCOUNT_ROLES.items())
    if identity != expected:
        raise RuntimeError('Live account identities differ from the canonical five accounts')
    return api, schema_guard(runtime)


def initial_guard(runtime, model):
    # Reuse the canonical seed definitions/comparator, leaving the old 69-table
    # cold guard untouched. The retained runtime seed predates the strict scalar
    # parser and contains account-password SQL expressions. Never execute it.
    base = schema_model()
    records = base_records()
    actual = {table: decoded(table_rows(runtime, table, columns), columns)
              for table, columns in base.items()}
    for account in records['sys_user']:
        current = next((row for row in actual['sys_user'] if row['id'] == account['id']), {})
        expected_length = ((len(account['username'].encode()) // 8) + 1) * 16
        if (not re.fullmatch('[0-9a-f]{8}', current.get('salt') or '')
                or not re.fullmatch('[0-9a-f]{' + str(expected_length) + '}', current.get('password') or '')):
            raise RuntimeError('Synthetic account credential encoding changed')
        account['salt'], account['password'] = current['salt'], current['password']
    expected = complete_records(base, records)
    actual['sys_log'] = []  # Retained normal synthetic audit history.
    config = actual.pop('sys_config')
    if (len(config) != 1 or config[0]['id'] != 'fixture_allow_registration'
            or config[0]['config_key'] != 'allowReg' or config[0]['config_value'] != '1'
            or config[0]['config_enabled'] != '1'):
        raise RuntimeError('Unexpected synthetic registration configuration')
    base.pop('sys_config'); expected.pop('sys_config')
    # Quartz initialises its reserved lock row even with auto-startup=false;
    # no jobs or scheduler state may be present. Retain this existing lock.
    quartz = actual['qrtz_locks']
    if len(quartz) > 1 or any({name.lower(): value for name, value in row.items()} !=
            {'sched_name': 'MyScheduler', 'lock_name': 'TRIGGER_ACCESS'} for row in quartz):
        raise RuntimeError('Unexpected scheduler lock rows')
    actual['qrtz_locks'] = []
    for record in actual['sys_user']:
        allowed_org = ('A99' if record['id'] == 'fixture_admin' else
                       'A99A01' if record['id'].endswith('_a') else 'A99A02')
        if record['org_code'] not in (None, '', allowed_org):
            raise RuntimeError('Synthetic user organisation escaped its assigned class')
        record['org_code'] = None
        if record['update_by'] not in (None, '', record['id']):
            raise RuntimeError('Unexpected synthetic account update actor')
        if record['update_time'] is not None and not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', record['update_time']):
            raise RuntimeError('Unexpected synthetic account update timestamp')
        record['update_by'] = record['update_time'] = None
    compare_records(base, actual, expected)
    for table in ('teaching_registration_profile', 'teaching_unit_view_event', 'teaching_work_event'):
        if table_rows(runtime, table, model[table]):
            raise RuntimeError('Preserve existing journey/event rows before preparing a new fixture')
    cutover = decoded(table_rows(runtime, 'teaching_work_event_cutover', model['teaching_work_event_cutover']),
                      model['teaching_work_event_cutover'])
    state = decoded(table_rows(runtime, 'sys_local_file_reference_state', model['sys_local_file_reference_state']),
                    model['sys_local_file_reference_state'])
    if len(cutover) != 1 or cutover[0]['id'] != '1' or len(state) != 1 or state[0]['id'] != '1':
        raise RuntimeError('Missing synthetic migration cutover/index state')
    for record in decoded(table_rows(runtime, 'sys_local_file_reference', model['sys_local_file_reference']),
                          model['sys_local_file_reference']):
        if record['source_id'] not in {'fixture_course_a', 'fixture_course_b', 'fixture_unit_a',
                'fixture_unit_b', 'fixture_additional_a', 'fixture_additional_b', 'fixture_allow_registration'}:
            raise RuntimeError('Unexpected synthetic media index source')
    expected_files = {f'fixture-work-{suffix}.txt': {
        'bytes': len(('synthetic work ' + suffix + '\n').encode()),
        'sha256': hashlib.sha256(('synthetic work ' + suffix + '\n').encode()).hexdigest()}
        for suffix in ('a', 'b')}
    if file_inventory(runtime / 'uploads') != expected_files:
        raise RuntimeError('Expected the two unchanged baseline synthetic upload files')


def ui_records():
    records = {table: [] for table in ('sys_permission', 'sys_role_permission', 'sys_dict', 'sys_dict_item')}
    selected = {'center', 'mine_work', 'my_task', 'work_list', 'task_list'}
    for index, (key, title, url, component, roles, hidden) in enumerate(ROUTES):
        if key not in selected:
            continue
        pid = PREFIX + key
        records['sys_permission'].append(dict(id=pid, parent_id='', name=title, url=url,
            component=component, menu_type=0, sort_no=index + 1, is_route=1, is_leaf=1,
            keep_alive=0, hidden=int(hidden), del_flag=0, status='1', internal_or_external=0))
        for role in roles:
            records['sys_role_permission'].append(dict(id=PREFIX + 'rp_' + role[0] + '_' + key,
                role_id='fixture_role_' + role, permission_id=pid))
    for dictionary_index, code in enumerate(('work_type', 'work_status', 'additional_work_status', 'sex', 'user_status', 'yn')):
        did = PREFIX + 'dict_' + str(dictionary_index)
        records['sys_dict'].append(dict(id=did, dict_name=code, dict_code=code, del_flag=0, type=0))
        for index, (value, label) in enumerate(DICT_ITEMS[code]):
            records['sys_dict_item'].append(dict(id=did + '_' + str(index), dict_id=did,
                item_text=label, item_value=value, sort_order=index, status=1))
    return records


def value_sql(value):
    return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + ' USING utf8mb4)' if str(value) else "''"


def insert_sql(table, row):
    if table not in TABLES:
        raise RuntimeError('Unreviewed fixture write table')
    return 'INSERT INTO teachingopen_dev.' + ident(table) + ' (' + ','.join(ident(k) for k in row) + ') VALUES (' + ','.join(value_sql(v) for v in row.values()) + ');'


def write_sql(runtime, query):
    # Restore contains private user hashes. Keep SQL off process argument lists.
    result = subprocess.run(mysql_command(runtime) + ['--raw'], input=query,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        diagnostic = runtime / 'logs' / ('teaching-journey-sql-error-' + str(time.time_ns()) + '.log')
        private_write(diagnostic, result.stderr or 'Selected transaction failed without diagnostics\n')
        raise RuntimeError('Selected synthetic SQL transaction failed; private diagnostic: ' + str(diagnostic))


def cache_scope(key):
    return (key in {'departLog:addiWorkAssign:fixture_class_a', 'departLog:addiWorkAssign:fixture_class_b'}
            or key in {'sys:cache:user::' + actor for actor in ACCOUNT_ROLES}
            or key.startswith(('sys:cache:dict::', 'sys:cache:dictTable::',
                              'sys:cache:depart:alldata::', 'sys:cache:depart:allids::')))


def cache_keys(api):
    return sorted(key for key in api.cache('KEYS', '*').splitlines() if cache_scope(key))


def cache_snapshot(api):
    result = {}
    for key in cache_keys(api):
        dumped = subprocess.check_output(api.redis + ['-n', '1', 'DUMP', key], env=api.redis_env)
        if not dumped.endswith(b'\n'):
            raise RuntimeError('Unexpected Redis dump framing')
        ttl = int(api.cache('PTTL', key))
        if ttl == -2:
            continue
        result[key] = {'dump': base64.b64encode(dumped[:-1]).decode(),
                       'expires_ms': None if ttl == -1 else int(time.time() * 1000) + ttl}
    return result


def redis_resp(parts):
    parts = [part if isinstance(part, bytes) else str(part).encode() for part in parts]
    return b'*' + str(len(parts)).encode() + b'\r\n' + b''.join(
        b'$' + str(len(part)).encode() + b'\r\n' + part + b'\r\n' for part in parts)


def restore_cache(api, saved):
    if any(not cache_scope(key) for key in saved):
        raise RuntimeError('Private snapshot contains an unreviewed cache key')
    commands = b''
    for key in sorted(set(cache_keys(api)) | set(saved)):
        commands += redis_resp(('DEL', key))
        record = saved.get(key)
        if record is not None:
            ttl = 0 if record['expires_ms'] is None else record['expires_ms'] - int(time.time() * 1000)
            if record['expires_ms'] is None or ttl > 0:
                commands += redis_resp(('RESTORE', key, ttl, base64.b64decode(record['dump'], validate=True)))
    if commands:
        result = subprocess.run(api.redis + ['-n', '1', '--pipe'], env=api.redis_env,
                                input=commands, capture_output=True, check=True)
        if b'errors: 0,' not in result.stdout:
            raise RuntimeError('Selected synthetic cache restoration failed')


def capture(runtime, api, model, dist):
    root = runtime / 'config' / BACKUP_NAME
    root.mkdir(mode=0o700)  # An incomplete or prior backup is never overwritten.
    files = file_inventory(runtime / 'uploads')
    (root / 'uploads').mkdir(mode=0o700)
    for name in files:
        target = root / 'uploads' / name
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        private_write(target, (runtime / 'uploads' / name).read_bytes())
    all_rows = {table: table_rows(runtime, table, columns) for table, columns in model.items()}
    snapshot = {'format': FORMAT, 'kind': KIND, 'runtime': str(runtime), 'ports': api.ports,
        'jar_sha256': api.jar_sha256, 'dist_sha256': digest(file_inventory(dist)),
        'created_unix': int(time.time()), 'tables': {table: {'columns': list(model[table]),
            'rows': all_rows[table]} for table in TABLES},
        'schema': {table: digest(sql(runtime, 'SHOW CREATE TABLE teachingopen_dev.' + ident(table)))
                   for table in model},
        'unaffected': {table: digest(rows) for table, rows in all_rows.items()
                       if table not in TABLES and table != 'sys_log'},
        'uploads': files, 'cache': cache_snapshot(api)}
    private_write(root / 'snapshot.json', json.dumps(snapshot, ensure_ascii=False) + '\n')
    private_write(root / 'snapshot.sha256', sha256(root / 'snapshot.json') + '\n')
    if file_inventory(runtime / 'uploads') != files:
        raise RuntimeError('Uploads changed while the private snapshot was captured')
    return snapshot


def load_snapshot(runtime):
    root = runtime / 'config' / BACKUP_NAME
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise RuntimeError('Expected the private teaching journey backup directory')
    path = private_file(root / 'snapshot.json')
    if sha256(path) != private_file(root / 'snapshot.sha256').read_text().strip():
        raise RuntimeError('Private teaching journey snapshot changed')
    snapshot = json.loads(path.read_text())
    if (snapshot.get('format') != FORMAT or snapshot.get('kind') != KIND
            or snapshot.get('runtime') != str(runtime) or snapshot.get('ports') != EXPECTED_PORTS
            or set(snapshot.get('tables', {})) != set(TABLES)):
        raise RuntimeError('Snapshot does not belong to this exact synthetic fixture')
    return snapshot


def restore_sql(snapshot, model):
    commands = ['SET NAMES utf8mb4;', 'START TRANSACTION;']
    for table in reversed(TABLES):
        commands.append('DELETE FROM teachingopen_dev.' + ident(table) + ';')
    for table in TABLES:
        record = snapshot['tables'][table]
        if record['columns'] != list(model[table]):
            raise RuntimeError('Snapshot columns escaped the reviewed schema')
        for row in record['rows']:
            if len(row) != len(record['columns']) or any(v is not None and not re.fullmatch(r'(?:[0-9A-Fa-f]{2})*', v) for v in row):
                raise RuntimeError('Invalid private snapshot row encoding')
            values = ['NULL' if v is None else "''" if not v else 'CONVERT(0x' + v + ' USING utf8mb4)' for v in row]
            commands.append('INSERT INTO teachingopen_dev.' + ident(table) + ' (' +
                ','.join(ident(name) for name in record['columns']) + ') VALUES (' + ','.join(values) + ');')
    commands.append('COMMIT;')
    return '\n'.join(commands)


def new_uploads(runtime, baseline):
    current = file_inventory(runtime / 'uploads')
    if any(current.get(name) != info for name, info in baseline.items()):
        raise RuntimeError('A baseline upload changed or disappeared; preserve the private backup for recovery')
    return sorted(set(current) - set(baseline))


def restore(runtime, api, model, output):
    snapshot = load_snapshot(runtime)
    if snapshot['jar_sha256'] != api.jar_sha256:
        raise RuntimeError('Restore against the same candidate JAR used to capture the snapshot')
    current_schema = {table: digest(sql(runtime, 'SHOW CREATE TABLE teachingopen_dev.' + ident(table))) for table in model}
    if snapshot['schema'] != current_schema:
        raise RuntimeError('Database schema changed; refusing an automatic data restore')
    for table, expected in snapshot['unaffected'].items():
        if digest(table_rows(runtime, table, model[table])) != expected:
            raise RuntimeError('An unrelated table changed; preserve it and investigate before restoring: ' + table)
    added = new_uploads(runtime, snapshot['uploads'])
    write_sql(runtime, restore_sql(snapshot, model))
    # SQL restoration is one transaction. Only files absent from the original
    # inventory are removed, after links/special files and baseline bytes pass.
    for name in added:
        (runtime / 'uploads' / name).unlink()
    root = runtime / 'uploads'
    for directory, _, _ in os.walk(root, topdown=False):
        path = Path(directory)
        if path != root and not any(path.iterdir()):
            path.rmdir()
    restore_cache(api, snapshot['cache'])
    restored = all(table_rows(runtime, table, model[table]) == snapshot['tables'][table]['rows'] for table in TABLES)
    uploads_restored = file_inventory(root) == snapshot['uploads']
    report = {'format': FORMAT, 'kind': KIND, 'jar_sha256': api.jar_sha256,
        'restored': restored and uploads_restored, 'tables': list(TABLES),
        'database_restored': restored, 'uploads_restored': uploads_restored,
        'removed_new_uploads': added, 'audit_table_preserved': 'sys_log',
        'selected_business_and_ui_cache_restored': True,
        'authentication_cache_note': 'Normal UI login sessions/CAPTCHA keys are retained until their ordinary expiry.'}
    private_write(output / ('fixture-cleanup-' + str(time.time_ns()) + '.json'), json.dumps(report, indent=2) + '\n')
    if not report['restored']:
        raise RuntimeError('Restoration readback differs; private snapshot retained')
    shutil.rmtree(runtime / 'config' / BACKUP_NAME)
    return report


def validate_records(model, records):
    complete_records(model, records)
    for table, rows in records.items():
        for row in rows:
            for name, value in row.items():
                match = re.fullmatch(r'(?:var)?char\((\d+)\)', model[table][name]['type'])
                if match and value is not None and len(str(value)) > int(match.group(1)):
                    raise RuntimeError('Fixed UI fixture field exceeds its reviewed SQL length: ' + table + '.' + name)


def prepare(runtime, model, api):
    records = ui_records()
    validate_records(model, records)
    commands = ['SET NAMES utf8mb4;', 'START TRANSACTION;']
    for table, rows in records.items():
        commands.extend(insert_sql(table, row) for row in rows)
    commands.append("UPDATE teachingopen_dev.sys_depart SET org_category='3' WHERE id IN ('fixture_class_a','fixture_class_b');")
    commands.append('COMMIT;')
    write_sql(runtime, '\n'.join(commands))
    for key in cache_keys(api):
        if not key.startswith('departLog:'):
            api.cache('DEL', key)
    # Menus/dictionaries/classes are not media reference sources. Do not rebuild
    # the index here, or before any business persistence assertion.


def state(runtime):
    fields = {
        'assignments': ('teaching_additional_work', ('id', 'work_name', 'work_desc', 'work_dept', 'status', 'code_type', 'create_by')),
        'works': ('teaching_work', ('id', 'user_id', 'depart_id', 'additional_id', 'course_id', 'work_name', 'work_type', 'work_status', 'work_file', 'work_cover', 'del_flag')),
        'feedback': ('teaching_work_correct', ('id', 'work_id', 'score', 'comment', 'create_by')),
        'comments': ('teaching_work_comment', ('id', 'work_id', 'user_id', 'comment')),
        'events': ('teaching_work_event', ('work_id', 'event_type', 'depart_id', 'event_state', 'counted_day')),
        'statistics': ('teaching_depart_day_log', ('id', 'depart_id', 'create_time', 'additional_work_assign_count', 'additional_work_submit_count', 'additional_work_correct_count', 'course_work_submit_count', 'course_work_correct_count')),
        'files': ('sys_file', ('id', 'file_name', 'file_path', 'file_location', 'create_by', 'del_flag')),
        'work_history': ('sys_data_log', ('id', 'data_table', 'data_id', 'data_version', 'create_by', 'create_time')),
        'media_references': ('sys_local_file_reference', ('source_type', 'source_id', 'field_name', 'reference_kind', 'reference_hash', 'reference_value')),
        'media_index_state': ('sys_local_file_reference_state', ('id', 'version', 'static_domain')),
    }
    result = {name: decoded(table_rows(runtime, table, columns), columns)
              for name, (table, columns) in fields.items()}
    result['counts'] = {name: len(rows) for name, rows in result.items()}
    return result


def allowed_request(headers, port):
    allowed_hosts = {host + ':' + str(port) for host in ('127.0.0.1', 'localhost')}
    hosts, origins = headers.get_all('Host', []), headers.get_all('Origin', [])
    return (len(hosts) == 1 and hosts[0] in allowed_hosts
            and (not origins or len(origins) == 1 and origins[0] in {'http://' + host for host in allowed_hosts}))


def material(api, actor, nonce):
    if actor not in ACTORS or not re.fullmatch('[A-Za-z0-9_.-]{1,100}', nonce):
        raise ValueError('Only four synthetic actors and a bounded CAPTCHA nonce are accepted')
    def find_code():
        for key in api.cache('KEYS', '*').splitlines():
            if re.fullmatch('[a-fA-F0-9]{32}', key):
                try:
                    value = json.loads(api.cache('GET', key))
                except ValueError:
                    continue
                if isinstance(value, str) and hashlib.md5((value + nonce).encode()).hexdigest().lower() == key.lower():
                    return value
    code = find_code()
    if code is None:
        status, image, _ = api.request('GET', '/sys/randomImage/' + nonce)
        if status != 200 or not image or not image.get('success'):
            raise RuntimeError('Actual local CAPTCHA generation failed')
        code = find_code()
    if code is None:
        raise RuntimeError('Actual CAPTCHA is missing from the owned Redis instance')
    return {'username': 'fixture_' + actor, 'password': api.credentials['test_user_password'],
            'captcha': code, 'checkKey': nonce}


def handler_class(api):
    class Handler(frontend.LocalFrontend):
        ports = api.ports

        def log_message(self, *_):
            # Never log paths, queries, tokens or synthetic login material.
            pass

        def parse_request(self):
            if not super().parse_request():
                return False
            if not allowed_request(self.headers, self.ports['frontend']):
                self.send_error(403, 'Only the corresponding local Host and Origin are accepted')
                return False
            return True

        def json_response(self, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlsplit(self.path)
            if route.path == '/__fixture/material':
                query = parse_qs(route.query, keep_blank_values=True)
                if set(query) != {'actor', 'nonce'} or any(len(values) != 1 for values in query.values()):
                    self.send_error(400, 'Expected one actor and nonce'); return
                try:
                    data = material(api, query['actor'][0], query['nonce'][0])
                except ValueError:
                    self.send_error(400, 'Invalid synthetic actor or nonce'); return
                except (RuntimeError, subprocess.SubprocessError):
                    self.send_error(503, 'Actual local CAPTCHA unavailable'); return
                self.json_response(data)
            elif route.path == '/__fixture/state':
                if route.query:
                    self.send_error(400, 'This read-only state route takes no parameters'); return
                self.json_response(state(api.runtime))
            elif route.path.startswith('/__fixture'):
                self.send_error(404, 'Unknown fixture route')
            else:
                super().do_GET()

        def do_HEAD(self):
            if urlsplit(self.path).path.startswith('/__fixture'):
                self.send_error(405, 'Fixture routes only support GET')
            else:
                super().do_HEAD()

        def mutate(self):
            if not self.path.startswith('/api/'):
                self.send_error(405, 'Only real /api requests are proxied'); return
            super().api()

        do_POST = mutate
        do_PUT = mutate
        do_DELETE = mutate
        do_OPTIONS = mutate
    return Handler


def assert_frontend_free(port):
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError('The dedicated frontend port must be free')


def run(args):
    runtime, jar, dist, output = map(checked_path, (args.runtime, args.jar, args.dist, args.output))
    if runtime != EXPECTED_RUNTIME or not runtime.is_dir() or runtime.stat().st_mode & 0o077:
        raise RuntimeError('Only the private media-index-1011 synthetic runtime is supported')
    if not (dist / 'index.html').is_file():
        raise RuntimeError('Provide the selected built frontend dist')
    file_inventory(dist)
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    with lock(runtime):
        api, model = runtime_guard(runtime, jar)
        assert_frontend_free(api.ports['frontend'])
        if args.restore:
            report = restore(runtime, api, model, output)
            print('TEACHING_JOURNEY_RESTORED', report['restored'], flush=True)
            return
        initial_guard(runtime, model)
        server = ThreadingHTTPServer(('127.0.0.1', api.ports['frontend']),
            functools.partial(handler_class(api), directory=str(dist)))
        captured = False
        try:
            capture(runtime, api, model, dist)
            captured = True
            prepare(runtime, model, api)
            ready = {'format': FORMAT, 'kind': KIND, 'runtime': str(runtime), 'ports': api.ports,
                'jar_sha256': api.jar_sha256, 'dist_sha256': digest(file_inventory(dist)),
                'fixture_tables': list(TABLES), 'assignment_submission_feedback_precreated': False,
                'audit_table_excluded_from_restore': 'sys_log',
                'stop': 'SIGINT/SIGTERM restores after closing the frontend; --restore recovers after SIGKILL.'}
            private_write(output / ('fixture-ready-' + str(time.time_ns()) + '.json'), json.dumps(ready, indent=2) + '\n')
            def stop(*_):
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGINT, stop)
            signal.signal(signal.SIGTERM, stop)
            print('TEACHING_JOURNEY_READY', api.ports['frontend'], flush=True)
            server.serve_forever()
        finally:
            server.server_close()
            if captured:
                # Reconfirm the running candidate and owned stores before writes.
                check_api, check_model = runtime_guard(runtime, jar)
                report = restore(runtime, check_api, check_model, output)
                print('TEACHING_JOURNEY_RESTORED', report['restored'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'dist', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--restore', action='store_true', help='Recover the retained private snapshot after an interrupted run')
    run(parser.parse_args())
