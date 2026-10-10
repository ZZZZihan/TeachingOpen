#!/usr/bin/env python3
"""Narrow owned real role-modal HTTP/DB regression, with complete restoration."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write

spec = importlib.util.spec_from_file_location('member_live_helpers', Path(__file__).with_name('class-member-context-live.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def role_state(runtime, prefix):
    if not re.fullmatch('memberrole_[a-f0-9]{8}', prefix or ''):
        raise ValueError('Only an owned role namespace is accepted')
    counts = {key: int(helpers.sql(runtime, 'SELECT COUNT(*) FROM sys_depart_role_user WHERE user_id=' + helpers.literal('fixture_student_a') + ' AND drole_id=' + helpers.literal(prefix + '_' + key))) for key in ('Aold', 'Anew', 'Bold')}
    return {**{key: value == 1 for key, value in counts.items()}, 'counts': counts}


def verify(args):
    runtime = helpers.owned(args)
    if hashlib.sha256(args.jar.read_bytes()).hexdigest() != helpers.JAR_SHA or (args.ref and args.ref != helpers.OLD_REF) or args.output.exists():
        raise ValueError('Use frozen JAR, specified source and a fresh evidence path')
    lock = runtime / 'class-member-context-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    prefix = 'memberrole_' + uuid4().hex[:8]
    roles = {key: prefix + '_' + key for key in ('Aold', 'Anew', 'Bold')}
    report = {'cases': []}
    try:
        with FixtureApi(runtime, args.jar) as client:
            before, attachments = database_inventory(runtime), file_inventory(runtime / 'uploads')
            users = helpers.snapshot(runtime, 'sys_user')
            membership = helpers.snapshot(runtime, 'sys_user_depart')
            if len(before) != 69 or len(users[1]) != 5 or helpers.sql(runtime, 'SELECT COUNT(*) FROM sys_depart_role') != '0' or helpers.sql(runtime, 'SELECT COUNT(*) FROM sys_depart_role_user') != '0':
                raise ValueError('Expected fresh owned role fixtures')
            private_write(runtime / 'config' / ('member-role-snapshot-' + uuid4().hex[:12] + '.json'), json.dumps({'sys_user': users, 'sys_user_depart': membership}))
            def check(name, passed):
                report['cases'].append({'case': name, 'passed': bool(passed)})
            try:
                helpers.sql(runtime, 'INSERT INTO sys_user_depart (id,user_id,dep_id) VALUES (' + ','.join(map(helpers.literal, (prefix + '_memberB', 'fixture_student_a', 'fixture_class_b'))) + ')')
                for key, role in roles.items():
                    department = 'fixture_class_b' if key == 'Bold' else 'fixture_class_a'
                    helpers.sql(runtime, 'INSERT INTO sys_depart_role (id,depart_id,role_name,role_code) VALUES (' + ','.join(map(helpers.literal, (role, department, 'Owned ' + key, role))) + ')')
                for key in ('Aold', 'Bold'):
                    helpers.sql(runtime, 'INSERT INTO sys_depart_role_user (id,user_id,drole_id) VALUES (' + ','.join(map(helpers.literal, (prefix + '_assign' + key, 'fixture_student_a', roles[key]))) + ')')
                client.login('admin')
                wrapper = Path(__file__).resolve()
                probe = wrapper.parents[2] / 'web/tests/class-member-role-live.cjs'
                config = {'origin': 'http://127.0.0.1:18178', 'runtime': str(runtime), 'wrapper': str(wrapper), 'prefix': prefix,
                          'token': client.tokens['admin'], 'sourceRef': args.ref, 'userId': 'fixture_student_a', 'departId': 'fixture_class_a', 'roles': roles}
                run = subprocess.run(['node', str(probe), str(args.source.resolve())], input=json.dumps(config), capture_output=True, text=True, timeout=120)
                try:
                    report = json.loads(run.stdout)
                except ValueError:
                    report = {'cases': [], 'error': 'launcher emitted no sanitized JSON'}
                report.update(exit_code=run.returncode, jar_sha256=client.jar_sha256,
                              wrapper_sha256=hashlib.sha256(wrapper.read_bytes()).hexdigest(), probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest())
                check('role launcher completed without infrastructure errors', run.returncode in (0, 1) and 'error' not in report)
            except Exception as error:
                report.update(error='owned role fixture or launcher did not complete', error_type=type(error).__name__, exit_code=2)
                check('role fixture and launcher completed without errors', False)
            finally:
                client.close()
                role_ids = ','.join(map(helpers.literal, roles.values()))
                helpers.sql(runtime, 'DELETE FROM sys_depart_role_user WHERE drole_id IN (' + role_ids + ')')
                helpers.sql(runtime, 'DELETE FROM sys_depart_role WHERE id IN (' + role_ids + ')')
                helpers.restore_rows(runtime, 'sys_user_depart', membership, replace=True)
                helpers.restore_rows(runtime, 'sys_user', users)
            after = database_inventory(runtime)
            report['restoration'] = {
                'table_count': len(before), 'non_audit_table_count': len(before) - 1, 'same_table_set': before.keys() == after.keys(),
                'changed_schemas': [table for table in before if before[table]['schema_sha256'] != after.get(table, {}).get('schema_sha256')],
                'changed_non_audit_tables': [table for table in before if table != 'sys_log' and before[table] != after.get(table)],
                'all_attachment_entries_equal': attachments == file_inventory(runtime / 'uploads')
            }
            restored = report['restoration']
            check('69 schemas 68 non-audit row sets and all attachments restored', restored['same_table_set'] and not restored['changed_schemas'] and not restored['changed_non_audit_tables'] and restored['all_attachment_entries_equal'])
            report['total'] = len(report['cases'])
            report['passed'] = sum(test['passed'] for test in report['cases'])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({key: report[key] for key in ('passed', 'total', 'exit_code', 'restoration')}))
            return 0 if report['passed'] == report['total'] and report['exit_code'] == 0 else 1
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--db-state', action='store_true')
    parser.add_argument('--prefix')
    for name in ('jar', 'source', 'output'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--ref')
    args = parser.parse_args()
    if args.db_state:
        print(json.dumps(role_state(helpers.owned(args), args.prefix), sort_keys=True))
    else:
        if any(getattr(args, name) is None for name in ('jar', 'source', 'output')):
            parser.error('--jar --source --output required')
        raise SystemExit(verify(args))
