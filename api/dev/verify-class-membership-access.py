#!/usr/bin/env python3
"""Real membership authorization/transaction checks in one owned synthetic runtime."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from uuid import uuid4

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write
from local_runtime import assert_database, load_ports, mysql_command

PORTS = {'mysql': 13373, 'redis': 16446, 'backend': 18181, 'frontend': 18182}
ACTORS = ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')
USERS = {actor: 'fixture_' + actor for actor in ACTORS}
A, B = 'fixture_class_a', 'fixture_class_b'


def literal(value):
    return "''" if str(value) == '' else 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def sql(runtime, query):
    result = subprocess.run(mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', query], capture_output=True, text=True, timeout=25)
    if result.returncode:
        private_write(runtime / 'logs' / ('membership-sql-' + uuid4().hex[:10] + '.log'), result.stderr)
        raise RuntimeError('Owned synthetic SQL failed; inspect private log')
    return result.stdout.rstrip('\n')


def snapshot(runtime, table):
    columns = [row.split('\t')[0] for row in sql(runtime, 'SHOW COLUMNS FROM ' + table).splitlines()]
    if any(not column.replace('_', '').isalnum() for column in columns):
        raise ValueError('Unexpected schema')
    expression = ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'~')" for column in columns)
    rows = [row.split('\t')[1:] for row in sql(runtime, "SELECT 'ROW'," + expression + ' FROM ' + table + ' ORDER BY id').splitlines()]
    return columns, rows


def restore(runtime, table, saved, replace=False):
    columns, rows = saved
    encode = lambda value: 'NULL' if value == '~' else "''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)'
    identity = next(i for i, name in enumerate(columns) if name.lower() == 'id')
    if replace:
        sql(runtime, 'DELETE FROM ' + table + ' WHERE user_id IN (' + ','.join(map(literal, USERS.values())) + ')')
    for row in rows:
        if replace:
            sql(runtime, 'INSERT INTO ' + table + ' (`' + '`,`'.join(columns) + '`) VALUES (' + ','.join(map(encode, row)) + ')')
        else:
            values = ['`' + col + '`=' + encode(value) for col, value in zip(columns, row) if col.lower() != 'id']
            sql(runtime, 'UPDATE ' + table + ' SET ' + ','.join(values) + ' WHERE id=' + encode(row[identity]))


def verify(args):
    runtime = args.runtime.absolute()
    if runtime != runtime.resolve() or runtime.parent.name != '.devspace' or runtime.name != 'class-membership-access-1003' or load_ports(runtime) != PORTS:
        raise ValueError('Only the owned membership runtime is accepted')
    if args.output.exists():
        raise ValueError('Preserve old evidence; choose a new output')
    assert_database(runtime)
    lock = runtime / 'membership-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    prefix = 'member_' + uuid4().hex[:8]
    role_a, role_b = prefix + '_a', prefix + '_b'
    trigger, ledger = prefix + '_fault', prefix + '_events'
    report = {'cases': [], 'scope': 'Real local HTTP and MySQL, synthetic accounts only; no browser or production acceptance.'}
    try:
        with FixtureApi(runtime, args.jar) as api:
            before, attachments = database_inventory(runtime), file_inventory(runtime / 'uploads')
            saved = {table: snapshot(runtime, table) for table in ('sys_user', 'sys_role', 'sys_user_depart')}
            if len(before) != 69 or len(saved['sys_user'][1]) != 5 or len(saved['sys_role'][1]) != 3 or sql(runtime, 'SELECT COUNT(*) FROM sys_depart_role') != '0' or sql(runtime, 'SELECT COUNT(*) FROM sys_depart_role_user') != '0':
                raise ValueError('Expected fresh five-account synthetic fixture')
            private_write(runtime / 'config' / (prefix + '-snapshot.json'), json.dumps(saved))

            def check(name, passed, reply=None, **detail):
                case = {'case': name, 'passed': bool(passed), **detail}
                if reply is not None:
                    case.update(http_status=reply[0], code=reply[1].get('code') if isinstance(reply[1], dict) else None)
                report['cases'].append(case)
                print(('PASS ' if passed else 'FAIL ') + name, flush=True)

            def accepted(reply):
                return reply[0] == 200 and isinstance(reply[1], dict) and reply[1].get('success') is True

            def rejected(reply):
                return reply[0] in (400, 401, 403) or (isinstance(reply[1], dict) and reply[1].get('success') is False)

            def call(kind, actor='admin', depart=A, users=None):
                users = ['fixture_student_a'] if users is None else users
                if kind == 'clear':
                    return api.request('GET', '/sys/sysDepart/removeAll?' + urlencode({'id': depart}), actor)
                if kind == 'add':
                    return api.request('POST', '/sys/user/editSysDepartWithUser', actor, {'depId': depart, 'userIdList': users})
                if kind == 'one':
                    return api.request('DELETE', '/sys/user/deleteUserInDepart?' + urlencode({'depId': depart, 'userId': users[0]}), actor)
                value = users if isinstance(users, str) else ','.join(users) + ','
                return api.request('DELETE', '/sys/user/deleteUserInDepartBatch?' + urlencode({'depId': depart, 'userIds': value}), actor)

            def count(table, where):
                return int(sql(runtime, 'SELECT COUNT(*) FROM ' + table + ' WHERE ' + where))

            def relation(depart, actor):
                return count('sys_user_depart', 'dep_id=' + literal(depart) + ' AND user_id=' + literal(USERS[actor]))

            def department_role(role):
                return count('sys_depart_role_user', 'drole_id=' + literal(role))

            def state():
                return {table: hashlib.sha256(json.dumps(snapshot(runtime, table)).encode()).hexdigest() for table in ('sys_user_depart', 'sys_depart_role_user', 'sys_user', 'sys_user_role')}

            def reset():
                restore(runtime, 'sys_user_depart', saved['sys_user_depart'], replace=True)
                sql(runtime, 'DELETE FROM sys_depart_role_user WHERE drole_id IN (' + literal(role_a) + ',' + literal(role_b) + ')')
                sql(runtime, 'INSERT INTO sys_user_depart (id,user_id,dep_id) VALUES (' + ','.join(map(literal, (prefix + '_shared', USERS['student_a'], B))) + ')')
                for suffix, role in (('a', role_a), ('b', role_b)):
                    sql(runtime, 'INSERT INTO sys_depart_role_user (id,user_id,drole_id) VALUES (' + ','.join(map(literal, (prefix + '_assign_' + suffix, USERS['student_a'], role))) + ')')

            def reauthenticate_admin():
                if 'admin' in api.tokens:
                    api.request('GET', '/sys/logout', 'admin')
                    api.tokens.pop('admin', None)
                for key in api.cache('KEYS', '*fixture_admin*').splitlines():
                    api.cache('DEL', key)
                api.login('admin')

            try:
                for name, level in (('admin', 9), ('teacher', 5), ('student', 1)):
                    sql(runtime, 'UPDATE sys_role SET role_level=' + str(level) + ' WHERE id=' + literal('fixture_role_' + name))
                for role, depart in ((role_a, A), (role_b, B)):
                    sql(runtime, 'INSERT INTO sys_depart_role (id,depart_id,role_name,role_code) VALUES (' + ','.join(map(literal, (role, depart, 'Owned membership role', role))) + ')')
                for actor in ACTORS:
                    api.login(actor)
                for actor in (None, 'student_a', 'student_b', 'teacher_a', 'teacher_b'):
                    for kind in ('add', 'one', 'batch', 'clear'):
                        reset(); initial = state()
                        target = ['fixture_student_b'] if kind == 'add' else ['fixture_student_a']
                        reply = call(kind, actor, users=target)
                        check(str(actor or 'anonymous') + ' cannot ' + kind + ' A membership', rejected(reply) and state() == initial, reply)

                for role_code in ('admin', 'dev'):
                    sql(runtime, 'UPDATE sys_role SET role_code=' + literal(role_code) + ' WHERE id=\'fixture_role_admin\'')
                    reauthenticate_admin()
                    reset(); before_roles = department_role(role_b)
                    reply = call('add', users=['fixture_student_b', 'fixture_student_b'])
                    check(role_code + ' adds one existing account without duplicate relation', accepted(reply) and relation(A, 'student_b') == 1 and relation(B, 'student_b') == 1 and department_role(role_b) == before_roles, reply)
                    reply = call('add', users=['fixture_student_b'])
                    check(role_code + ' repeated add is idempotent', accepted(reply) and relation(A, 'student_b') == 1, reply)
                    for kind in ('one', 'batch', 'clear'):
                        reset(); initial = state(); reply = call(kind)
                        correct = relation(A, 'student_a') == 0 and relation(B, 'student_a') == 1 and department_role(role_a) == 0 and department_role(role_b) == 1
                        if kind == 'clear': correct = correct and relation(A, 'teacher_a') == 0
                        else: correct = correct and relation(A, 'teacher_a') == 1
                        current = state()
                        check(role_code + ' normal ' + kind + ' clears only target associations and department roles', accepted(reply) and correct and current['sys_user'] == initial['sys_user'] and current['sys_user_role'] == initial['sys_user_role'], reply)
                sql(runtime, "UPDATE sys_role SET role_code='admin' WHERE id='fixture_role_admin'")
                reauthenticate_admin()

                for kind in ('add', 'one', 'batch', 'clear'):
                    for invalid in ('', prefix + '_missing_dept'):
                        reset(); initial = state(); reply = call(kind, depart=invalid)
                        check(kind + ' rejects ' + ('empty' if not invalid else 'missing') + ' department unchanged', rejected(reply) and state() == initial, reply)
                for kind, users, label in (
                    ('add', [], 'empty users'), ('add', ['fixture_admin', prefix + '_missing_user'], 'mixed missing user'),
                    ('add', [''], 'blank user'), ('one', [prefix + '_missing_user'], 'missing user'),
                    ('batch', ['fixture_student_a', prefix + '_missing_user'], 'mixed missing user'),
                    ('batch', 'fixture_student_a,,fixture_teacher_a,', 'interior empty token'),
                    ('batch', ',,', 'empty users')):
                    reset(); initial = state(); reply = call(kind, users=users)
                    check(kind + ' rejects ' + label + ' atomically', rejected(reply) and state() == initial, reply)
                for kind in ('add', 'one', 'batch', 'clear'):
                    reset(); initial = state(); reply = call(kind, depart=A.upper())
                    check(kind + ' rejects department case alias unchanged', rejected(reply) and state() == initial, reply)
                for kind in ('add', 'one', 'batch'):
                    reset(); initial = state(); reply = call(kind, users=['FIXTURE_STUDENT_A'])
                    check(kind + ' rejects user case alias unchanged', rejected(reply) and state() == initial, reply)
                for kind in ('add', 'one', 'batch', 'clear'):
                    reset(); sql(runtime, "UPDATE sys_depart SET del_flag='1' WHERE id='fixture_class_a'")
                    try:
                        initial = state(); reply = call(kind)
                        check(kind + ' rejects deleted department unchanged', rejected(reply) and state() == initial, reply)
                    finally:
                        sql(runtime, "UPDATE sys_depart SET del_flag='0' WHERE id='fixture_class_a'")
                for kind in ('add', 'one', 'batch', 'clear'):
                    reset(); sql(runtime, "UPDATE sys_user SET del_flag=1 WHERE id='fixture_student_a'")
                    try:
                        initial = state(); reply = call(kind)
                        check(kind + ' rejects deleted user without partial mutation', rejected(reply) and state() == initial, reply)
                    finally:
                        restore(runtime, 'sys_user', saved['sys_user'])
                for kind, users in (('one', ['fixture_student_b']), ('batch', ['fixture_student_a', 'fixture_student_b'])):
                    reset(); initial = state(); reply = call(kind, users=users)
                    check(kind + ' rejects nonmember atomically', rejected(reply) and state() == initial, reply)
                reset(); reply = call('batch', users='fixture_student_a,fixture_student_a,')
                check('batch accepts duplicate IDs and legacy trailing comma', accepted(reply) and relation(A, 'student_a') == 0 and relation(A, 'teacher_a') == 1, reply)

                sql(runtime, "UPDATE sys_role SET role_level=10 WHERE id='fixture_role_teacher'")
                for kind in ('one', 'batch', 'clear'):
                    reset(); initial = state(); target = ['fixture_teacher_a'] if kind == 'one' else ['fixture_student_a', 'fixture_teacher_a']
                    reply = call(kind, users=target)
                    check(kind + ' refuses any higher-level target without partial removal', rejected(reply) and state() == initial, reply)
                sql(runtime, "UPDATE sys_role SET role_level=5 WHERE id='fixture_role_teacher'")

                # MyISAM ledger proves the injected trigger executed even when the
                # product's InnoDB transaction rolls back; it is removed finally.
                sql(runtime, 'CREATE TABLE ' + ledger + ' (id INT AUTO_INCREMENT PRIMARY KEY, marker VARCHAR(32)) ENGINE=MyISAM')
                for table, operation, target, kinds in (
                    ('sys_user_depart', 'INSERT', 'fixture_teacher_b', ('add',)),
                    ('sys_depart_role_user', 'DELETE', 'fixture_student_a', ('one', 'batch', 'clear')),
                    ('sys_user_depart', 'DELETE', 'fixture_student_a', ('one', 'batch', 'clear'))):
                    for kind in kinds:
                        reset(); initial = state(); sql(runtime, 'DELETE FROM ' + ledger)
                        alias = 'NEW' if operation == 'INSERT' else 'OLD'
                        condition = alias + '.user_id=' + literal(target)
                        condition += ' AND ' + alias + ('.dep_id=' + literal(A) if table == 'sys_user_depart' else '.drole_id=' + literal(role_a))
                        sql(runtime, 'DELIMITER //\nCREATE TRIGGER ' + trigger + ' BEFORE ' + operation + ' ON ' + table + ' FOR EACH ROW BEGIN IF ' + condition + ' THEN INSERT INTO ' + ledger + " (marker) VALUES ('owned membership fault'); SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='owned membership fault'; END IF; END//\nDELIMITER ;")
                        try:
                            reply = call(kind, users=['fixture_admin', 'fixture_teacher_b'] if kind == 'add' else ['fixture_student_a'])
                            fired = count(ledger, '1=1') > 0
                            check(kind + ' rolls back on ' + table + ' ' + operation + ' fault', rejected(reply) and fired and state() == initial, reply, injected_fault_reached=fired)
                            message = str(reply[1].get('message', '')) if isinstance(reply[1], dict) else ''
                            hidden = all(marker not in message for marker in ('owned membership fault', '###', 'SQL:', 'INSERT INTO', 'DELETE FROM'))
                            check(kind + ' hides SQL details on ' + table + ' ' + operation + ' fault', hidden, reply)
                        finally:
                            sql(runtime, 'DROP TRIGGER IF EXISTS ' + trigger)
                sql(runtime, 'DROP TABLE ' + ledger)
                reset()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    replies = list(pool.map(lambda _: call('add', users=['fixture_student_b']), range(2)))
                check('two concurrent adds leave one association', all(map(accepted, replies)) and relation(A, 'student_b') == 1)
            except Exception as error:
                report['infrastructure_error_type'] = type(error).__name__
                check('probe completed without infrastructure error', False)
            finally:
                sql(runtime, 'DROP TRIGGER IF EXISTS ' + trigger)
                sql(runtime, 'DROP TABLE IF EXISTS ' + ledger)
                api.close()
                sql(runtime, 'DELETE FROM sys_depart_role_user WHERE drole_id IN (' + literal(role_a) + ',' + literal(role_b) + ')')
                sql(runtime, 'DELETE FROM sys_depart_role WHERE id IN (' + literal(role_a) + ',' + literal(role_b) + ')')
                restore(runtime, 'sys_user_depart', saved['sys_user_depart'], replace=True)
                restore(runtime, 'sys_user', saved['sys_user'])
                restore(runtime, 'sys_role', saved['sys_role'])
            after = database_inventory(runtime)
            restoration = {'table_count': len(before), 'non_audit_table_count': len(before) - 1, 'same_table_set': before.keys() == after.keys(), 'changed_schemas': [t for t in before if before[t]['schema_sha256'] != after.get(t, {}).get('schema_sha256')], 'changed_non_audit_tables': [t for t in before if t != 'sys_log' and before[t] != after.get(t)], 'attachments_equal': attachments == file_inventory(runtime / 'uploads')}
            report['restoration'] = restoration
            check('all schemas non-audit rows and attachments restored', restoration['same_table_set'] and not restoration['changed_schemas'] and not restoration['changed_non_audit_tables'] and restoration['attachments_equal'])
            report.update(jar_sha256=api.jar_sha256, probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), total=len(report['cases']), passed=sum(c['passed'] for c in report['cases']))
            private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({key: report[key] for key in ('passed', 'total', 'jar_sha256', 'restoration')}))
            return 0 if report['passed'] == report['total'] else 1
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    raise SystemExit(verify(parser.parse_args()))
