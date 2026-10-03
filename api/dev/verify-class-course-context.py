#!/usr/bin/env python3
"""Real SFC method -> HTTP -> DB class-course context regressions.

Only the owned disposable runtime is accepted. Credentials reach the Node
method probe through stdin; no browser authentication or UI acceptance is claimed.
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
from local_runtime import load_ports, mysql_command

PORTS = {'mysql': 13371, 'redis': 16444, 'backend': 18175, 'frontend': 18176}
JAR_SHA = '4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42'
OLD_REF = '253f3fb4c44b500b6e4824adbf89da51ac89d50c'


def literal(value):
    return "''" if str(value) == '' else 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def verify(args):
    runtime = args.runtime.absolute()
    if runtime != runtime.resolve() or runtime.name != 'class-course-context-1003' or runtime.parent.name != '.devspace' or load_ports(runtime) != PORTS:
        raise ValueError('Only the owned class-course-context-1003 runtime is supported')
    if hashlib.sha256(args.jar.read_bytes()).hexdigest() != JAR_SHA:
        raise ValueError('Use the specified frozen encoded-media JAR')
    if args.ref and args.ref != OLD_REF:
        raise ValueError('Only the specified old source reference is supported')
    if args.output.exists():
        raise ValueError('Preserve evidence; use a new output path')
    lock = runtime / 'class-course-context-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    prefix = 'ctx_' + uuid4().hex[:10]
    courses = {key: prefix + '_c_' + str(i) for i, key in enumerate(('bulkPending', 'bulkAfterSwitch', 'baseB', 'crossSwitch', 'crossReopen', 'normal'))}
    relations = {key: prefix + '_r_' + str(i) for i, key in enumerate(('bulkPending', 'bulkAfterSwitch', 'baseB'))}
    course_ids = ','.join(map(literal, courses.values()))
    open_time = '2030-01-02 09:00:00'
    report = {'cases': []}
    try:
        with FixtureApi(runtime, args.jar) as client:
            def sql(query):
                result = subprocess.run(mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', query], capture_output=True, text=True, timeout=25)
                if result.returncode:
                    private_write(runtime / 'logs' / ('class-context-sql-failure-' + uuid4().hex[:10] + '.log'), result.stderr)
                    raise RuntimeError('Owned synthetic SQL operation failed')
                return result.stdout.rstrip('\n')

            def snapshot(table):
                columns = [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM ' + table).splitlines()]
                if any(not name.replace('_', '').isalnum() for name in columns):
                    raise ValueError('Unexpected table column')
                expression = ','.join("IFNULL(HEX(CAST(`" + col + "` AS BINARY)),'~')" for col in columns)
                rows = [row.split('\t')[1:] for row in sql("SELECT 'ROW'," + expression + ' FROM ' + table + ' ORDER BY id').splitlines()]
                return columns, rows

            def restore(table, saved):
                columns, rows = saved
                for row in rows:
                    assignments = []
                    for col, value in zip(columns, row):
                        if col != 'id':
                            expression = 'NULL' if value == '~' else "''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)'
                            assignments.append('`' + col + '`=' + expression)
                    sql('UPDATE ' + table + ' SET ' + ','.join(assignments) + ' WHERE id=CONVERT(0x' + row[columns.index('id')] + ' USING utf8mb4)')

            before, attachments = database_inventory(runtime), file_inventory(runtime / 'uploads')
            users, departments = snapshot('sys_user'), snapshot('sys_depart')
            if len(users[1]) != 5 or len(before) != 69 or sql('SELECT COUNT(*) FROM teaching_course WHERE id IN (' + course_ids + ')') != '0':
                raise ValueError('Expected the original five users, 69 tables and a fresh namespace')
            def check(name, passed, **details):
                report['cases'].append({'case': name, 'passed': bool(passed), **details})

            try:
                # The common seed has org_category=2; real class-course controls
                # require category 3. Change only these two owned rows and restore
                # their complete original snapshots after each source comparison.
                sql("UPDATE sys_depart SET org_category='3' WHERE id IN ('fixture_class_a','fixture_class_b')")
                for key, course_id in courses.items():
                    sql('INSERT INTO teaching_course (id,course_name,course_desc,show_home,is_shared,depart_ids,course_type,course_category) VALUES ('
                        + literal(course_id) + ',' + literal('Context ' + key) + ", 'Owned bounded method probe',1,0,'fixture_school','1','1')")
                for key in relations:
                    dept = 'fixture_class_b' if key == 'baseB' else 'fixture_class_a'
                    sql('INSERT INTO teaching_course_dept (id,dept_id,course_id,open_time) VALUES ('
                        + ','.join(map(literal, (relations[key], dept, courses[key], '2026-01-01 00:00:00'))) + ')')
                client.login('admin')
                config = {'origin': 'http://127.0.0.1:18175', 'token': client.tokens['admin'], 'sourceRef': args.ref,
                          'classes': {'A': 'fixture_class_a', 'B': 'fixture_class_b'}, 'courses': courses, 'relations': relations, 'openTime': open_time}
                probe = Path(__file__).resolve().parents[2] / 'web/tests/class-course-context-live.cjs'
                run = subprocess.run(['node', str(probe), str(args.source.resolve())], input=json.dumps(config), capture_output=True, text=True, timeout=180)
                try:
                    report = json.loads(run.stdout)
                except ValueError:
                    report = {'cases': [], 'error': 'launcher emitted no sanitized JSON', 'error_type': 'non-json-output'}
                report.update(exit_code=run.returncode, jar_sha256=client.jar_sha256,
                              probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                              scope='Actual SFC/Mixin methods and real HTTP/DB in an owned runtime; browser rendering and browser authentication excluded')
                for key in ('bulkPending', 'bulkAfterSwitch'):
                    check(key + ': DB A relationship preserved', sql('SELECT COUNT(*) FROM teaching_course_dept WHERE id=' + literal(relations[key])) == '1')
                for key in ('crossSwitch', 'crossReopen'):
                    check(key + ': DB has no stale A course attached to B', sql("SELECT COUNT(*) FROM teaching_course_dept WHERE dept_id='fixture_class_b' AND course_id=" + literal(courses[key])) == '0')
                check('normal B openTime verified directly in DB', sql('SELECT DATE_FORMAT(open_time,\'%Y-%m-%d %H:%i:%s\') FROM teaching_course_dept WHERE id=' + literal(relations['baseB'])) == open_time)
                check('normal B newly added relationship deleted in DB', sql('SELECT COUNT(*) FROM teaching_course_dept WHERE course_id=' + literal(courses['normal'])) == '0')
                check('method probe exited normally without launcher errors', run.returncode in (0, 1) and 'error' not in report)
            except Exception as error:
                report.update(error='fixture or launcher did not complete', error_type=type(error).__name__, exit_code=2, jar_sha256=client.jar_sha256)
                check('fixture and launcher completed without errors', False)
            finally:
                remaining = sql('SELECT id FROM teaching_course_dept WHERE course_id IN (' + course_ids + ')').splitlines()
                for relation_id in set(remaining + list(relations.values())):
                    sql('DELETE FROM sys_data_log WHERE data_id=' + literal(relation_id))
                sql('DELETE FROM teaching_course_dept WHERE course_id IN (' + course_ids + ')')
                sql('DELETE FROM teaching_course WHERE id IN (' + course_ids + ')')
                client.close()
                restore('sys_user', users)
                restore('sys_depart', departments)
            after = database_inventory(runtime)
            report['restoration'] = {'table_count': len(before), 'non_audit_table_count': len(before) - 1,
                                    'same_table_set': before.keys() == after.keys(),
                                    'changed_schemas': [t for t in before if before[t]['schema_sha256'] != after.get(t, {}).get('schema_sha256')],
                                    'changed_non_audit_tables': [t for t in before if t != 'sys_log' and before[t] != after.get(t)],
                                    'all_attachment_entries_equal': attachments == file_inventory(runtime / 'uploads')}
            restored = report['restoration']
            check('69 schemas 68 non-audit row sets and all attachments restored', restored['same_table_set'] and not restored['changed_schemas'] and not restored['changed_non_audit_tables'] and restored['all_attachment_entries_equal'])
            report['total'] = len(report['cases'])
            report['passed'] = sum(case['passed'] for case in report['cases'])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({key: report[key] for key in ('passed', 'total', 'exit_code', 'restoration')}))
            return 0 if report['passed'] == report['total'] and report['exit_code'] == 0 else 1
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ref', help='The specified old frontend source commit; omit to test current source')
    raise SystemExit(verify(parser.parse_args()))
