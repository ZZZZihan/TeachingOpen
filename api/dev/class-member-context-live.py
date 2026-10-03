#!/usr/bin/env python3
"""Owned member-context SFC methods, real HTTP and DB restoration evidence.

Credentials remain in the private runtime or subprocess stdin. This is neither
browser authentication nor a production authorization/security acceptance test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write
from local_runtime import load_ports, mysql_command, assert_database

PORTS = {'mysql': 13372, 'redis': 16445, 'backend': 18178, 'frontend': 18179}
JAR_SHA = '4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42'
OLD_REF = '8f58b32362899047da0136e41278368fd26c88f0'
USERS = {name: 'fixture_' + name for name in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')}
CLASSES = {'A': 'fixture_class_a', 'B': 'fixture_class_b'}


def literal(value):
    return "''" if str(value) == '' else 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def owned(args):
    runtime = args.runtime.absolute()
    if runtime != runtime.resolve() or runtime.name != 'class-member-context-1003' or runtime.parent.name != '.devspace' or load_ports(runtime) != PORTS:
        raise ValueError('Only the owned class-member-context-1003 runtime is supported')
    assert_database(runtime)
    return runtime


def sql(runtime, query):
    result = subprocess.run(mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', query], capture_output=True, text=True, timeout=25)
    if result.returncode:
        private_write(runtime / 'logs' / ('member-context-sql-failure-' + uuid4().hex[:10] + '.log'), result.stderr)
        raise RuntimeError('Owned synthetic SQL operation failed')
    return result.stdout.rstrip('\n')


def db_state(runtime):
    state = {'user_count': int(sql(runtime, 'SELECT COUNT(*) FROM sys_user'))}
    for label, department in CLASSES.items():
        state[label] = {'count': int(sql(runtime, 'SELECT COUNT(*) FROM sys_user_depart WHERE dep_id=' + literal(department)))}
        for alias, user in USERS.items():
            state[label][alias] = sql(runtime, 'SELECT COUNT(*) FROM sys_user_depart WHERE dep_id=' + literal(department) + ' AND user_id=' + literal(user)) == '1'
    return state


def snapshot(runtime, table):
    columns = [row.split('\t')[0] for row in sql(runtime, 'SHOW COLUMNS FROM ' + table).splitlines()]
    if any(not col.replace('_', '').isalnum() for col in columns):
        raise ValueError('Unexpected table column')
    expression = ','.join("IFNULL(HEX(CAST(`" + col + "` AS BINARY)),'~')" for col in columns)
    rows = [row.split('\t')[1:] for row in sql(runtime, "SELECT 'ROW'," + expression + ' FROM ' + table + ' ORDER BY id').splitlines()]
    return columns, rows


def value_sql(value):
    return 'NULL' if value == '~' else "''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)'


def restore_rows(runtime, table, saved, replace=False):
    columns, rows = saved
    identity = next(i for i, name in enumerate(columns) if name.lower() == 'id')
    if replace:
        user_ids = ','.join(map(literal, USERS.values()))
        sql(runtime, 'DELETE FROM ' + table + ' WHERE user_id IN (' + user_ids + ')')
    for row in rows:
        if replace:
            sql(runtime, 'INSERT INTO ' + table + ' (`' + '`,`'.join(columns) + '`) VALUES (' + ','.join(map(value_sql, row)) + ')')
        else:
            changes = ['`' + col + '`=' + value_sql(value) for col, value in zip(columns, row) if col.lower() != 'id']
            sql(runtime, 'UPDATE ' + table + ' SET ' + ','.join(changes) + ' WHERE `' + columns[identity] + '`=' + value_sql(row[identity]))


def verify(args):
    runtime = owned(args)
    if hashlib.sha256(args.jar.read_bytes()).hexdigest() != JAR_SHA:
        raise ValueError('Use the specified frozen encoded-media JAR')
    if args.ref and args.ref != OLD_REF:
        raise ValueError('Only the specified old source reference is supported')
    if args.output.exists():
        raise ValueError('Preserve evidence; use a new output path')
    lock = runtime / 'class-member-context-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    report = {'cases': [], 'observations_not_fixed': []}
    try:
        with FixtureApi(runtime, args.jar) as client:
            before, attachments = database_inventory(runtime), file_inventory(runtime / 'uploads')
            saved = {table: snapshot(runtime, table) for table in ('sys_user', 'sys_depart', 'sys_role', 'sys_user_depart', 'sys_depart_role_user')}
            if len(before) != 69 or len(saved['sys_user'][1]) != 5 or len(saved['sys_depart'][1]) != 3 or len(saved['sys_role'][1]) != 3:
                raise ValueError('Expected fresh synthetic fixtures and 69 tables')
            private_write(runtime / 'config' / ('member-context-snapshot-' + uuid4().hex[:12] + '.json'), json.dumps(saved))
            def check(name, passed, **details):
                report['cases'].append({'case': name, 'passed': bool(passed), **details})
            try:
                # Only three owned roles are changed to exercise real role-level
                # rejection; restore every column, not just role_level, afterward.
                for role, level in (('admin', 9), ('teacher', 5), ('student', 1)):
                    sql(runtime, 'UPDATE sys_role SET role_level=' + str(level) + ' WHERE id=' + literal('fixture_role_' + role))
                sql(runtime, "UPDATE sys_depart SET org_category='3' WHERE id IN ('fixture_class_a','fixture_class_b')")
                client.login('admin')
                client.login('student_a')
                wrapper = Path(__file__).resolve()
                probe = wrapper.parents[2] / 'web/tests/class-member-context-live.cjs'
                config = {'origin': 'http://127.0.0.1:18178', 'runtime': str(runtime), 'wrapper': str(wrapper),
                          'token': client.tokens['admin'], 'studentToken': client.tokens['student_a'], 'sourceRef': args.ref,
                          'classes': CLASSES, 'users': USERS}
                run = subprocess.run(['node', str(probe), str(args.source.resolve())], input=json.dumps(config), capture_output=True, text=True, timeout=240)
                try:
                    report = json.loads(run.stdout)
                except ValueError:
                    report = {'cases': [], 'error': 'launcher emitted no sanitized JSON', 'error_type': 'non-json-output'}
                report.update(exit_code=run.returncode, jar_sha256=client.jar_sha256,
                              wrapper_sha256=hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                              probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                              scope='Actual SFC/Mixin methods, owned real HTTP and immediate read-only DB checks; browser rendering excluded')
                check('method launcher completed without infrastructure errors', run.returncode in (0, 1) and 'error' not in report)
                # This frozen backend issue is observed separately, without
                # turning a backend authorization gap into a frontend green gate.
                baseline = db_state(runtime)
                status, payload, _ = client.request('GET', '/sys/sysDepart/removeAll?id=fixture_class_a', 'student_a')
                observed = db_state(runtime)
                report['observations_not_fixed'] = [{
                    'case': 'student direct removeAll request on owned synthetic class',
                    'actor_role': 'student', 'http_status': status, 'business_success': bool(payload and payload.get('success')),
                    'before_member_count': baseline['A']['count'], 'after_member_count': observed['A']['count'],
                    'accounts_preserved': observed['user_count'] == baseline['user_count'],
                    'boundary': 'Frozen backend behavior; not fixed or included in frontend assertion total.'
                }]
            except Exception as error:
                report.update(error='fixture or launcher did not complete', error_type=type(error).__name__, exit_code=2, jar_sha256=client.jar_sha256)
                check('fixture and launcher completed without errors', False)
            finally:
                client.close()
                for table in ('sys_user_depart', 'sys_depart_role_user'):
                    restore_rows(runtime, table, saved[table], replace=True)
                for table in ('sys_user', 'sys_depart', 'sys_role'):
                    restore_rows(runtime, table, saved[table])
            after = database_inventory(runtime)
            report['restoration'] = {
                'table_count': len(before), 'non_audit_table_count': len(before) - 1,
                'same_table_set': before.keys() == after.keys(),
                'changed_schemas': [table for table in before if before[table]['schema_sha256'] != after.get(table, {}).get('schema_sha256')],
                'changed_non_audit_tables': [table for table in before if table != 'sys_log' and before[table] != after.get(table)],
                'all_attachment_entries_equal': attachments == file_inventory(runtime / 'uploads')
            }
            restoration = report['restoration']
            check('69 schemas 68 non-audit row sets and all attachments restored', restoration['same_table_set'] and not restoration['changed_schemas'] and not restoration['changed_non_audit_tables'] and restoration['all_attachment_entries_equal'])
            report['total'] = len(report['cases'])
            report['passed'] = sum(case['passed'] for case in report['cases'])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({key: report[key] for key in ('passed', 'total', 'exit_code', 'restoration', 'observations_not_fixed')}))
            return 0 if report['passed'] == report['total'] and report['exit_code'] == 0 else 1
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--db-state', action='store_true', help='Read-only owned fixture relation matrix for the Node probe')
    for name in ('jar', 'source', 'output'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--ref')
    args = parser.parse_args()
    if args.db_state:
        print(json.dumps(db_state(owned(args)), sort_keys=True))
    else:
        if any(getattr(args, name) is None for name in ('jar', 'source', 'output')):
            parser.error('--jar --source --output are required for execution')
        raise SystemExit(verify(args))
