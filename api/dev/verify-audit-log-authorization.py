#!/usr/bin/env python3
"""H06: audit and version history must not bypass private-work authorization.

Requires exclusive access to a FixtureApi-owned synthetic runtime. Exercises the
actual allclear HTTP action, preserves the complete original audit table in
memory, and restores it after logging out. Never use production data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote

from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_h06_'
WORK = PREFIX + 'work'
SECRET = 'fixture-private-feedback-h06-8317'
TABLES = ('sys_log', 'sys_data_log', 'teaching_work', 'teaching_work_correct',
          'teaching_work_comment', 'teaching_work_event', 'teaching_depart_day_log', 'sys_user_role', 'sys_role')


def verify(args):
    if args.output.exists():
        raise RuntimeError('Preserve existing audit authorization evidence')
    cases, error = [], None
    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        if not passed:
            raise AssertionError(name)

    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev'], input=statement,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError('Synthetic audit SQL failed')
            return result.stdout.strip()
        def literal(value):
            return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)" if str(value) else "''"
        def insert(table, **values):
            sql('INSERT INTO ' + table + ' (' + ','.join(values) + ') VALUES (' + ','.join(literal(v) for v in values.values()) + ')')
        def digest():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY ' + ('work_id,event_type' if table == 'teaching_work_event' else 'id')).encode()).hexdigest() for table in TABLES}
        def capture(table):
            columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM ' + table).splitlines()]
            rows = sql('SELECT ' + ','.join("IFNULL(CONCAT('H',HEX(CAST(`" + column + "` AS BINARY))),'NULL')" for column in columns)
                       + ' FROM ' + table + ' ORDER BY id').splitlines()
            return columns, rows
        def restore(table, saved):
            columns, rows = saved
            statements = ['DELETE FROM ' + table]
            for row in rows:
                values = ['NULL' if cell == 'NULL' else "''" if cell == 'H' else 'CONVERT(0x' + cell[1:] + ' USING utf8mb4)' for cell in row.split('\t')]
                statements.append('INSERT INTO ' + table + ' (`' + '`,`'.join(columns) + '`) VALUES (' + ','.join(values) + ')')
            sql(';\n'.join(statements) + ';')
        def call(method, route, actor='admin', body=None):
            return api.request(method, route, actor, body)[:2]
        def allowed(name, method, route, actor='admin', body=None):
            status, result = call(method, route, actor, body)
            check(name, status == 200 and result and result.get('success') is True)
            return result
        def denied(name, method, route, actor, body=None):
            before = digest()
            status, result = call(method, route, actor, body)
            check(name + ' is an authorization refusal', status == (200 if actor else 401) and result
                  and result.get('success') is False and result.get('code') == (510 if actor else 401) and not result.get('result'))
            check(name + ' returns no private marker', SECRET not in json.dumps(result))
            check(name + ' leaves audit history work feedback and roles unchanged', before == digest())
        def history_reads(audit_id):
            return ['/sys/log/list?id=' + audit_id, '/sys/dataLog/list?dataId=' + WORK,
                    '/sys/dataLog/queryCompareList?dataId1=' + PREFIX + 'v1&dataId2=' + PREFIX + 'v2',
                    '/sys/dataLog/queryDataVerList?dataTable=teaching_work&dataId=' + WORK]
        def audit(suffix):
            ident = PREFIX + suffix
            insert('sys_log', id=ident, log_type=2, log_content='synthetic historical grading audit',
                   request_param=json.dumps({'workId':WORK, 'score':4, 'comment':SECRET}), userid='fixture_teacher_a')
            return ident

        for table in TABLES:
            column = 'work_id' if table == 'teaching_work_event' else 'id'
            if sql("SELECT COUNT(*) FROM " + table + " WHERE " + column + " LIKE '" + PREFIX + "%'") != '0':
                raise RuntimeError('Existing H06 fixtures must not be overwritten')
        original = digest()
        original_audit = capture('sys_log')
        original_daily = capture('teaching_depart_day_log')
        try:
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                api.login(actor)
            insert('teaching_work', id=WORK, user_id='fixture_student_a', depart_id='fixture_class_a',
                   work_name='synthetic private audit work', work_file='fixture_file_a', work_type='2',
                   work_status='1', work_scene='create', del_flag=0, create_by='fixture_student_a', create_time='2026-10-11 00:00:00')
            allowed('teacher grades own class through actual business API', 'PUT', '/teaching/teachingWork/edit', 'teacher_a',
                    {'id':WORK, 'workStatus':'2', 'teachingWorkCorrectList':[{'score':4, 'comment':SECRET}]})
            check('unique private feedback is committed', sql('SELECT comment FROM teaching_work_correct WHERE work_id=' + literal(WORK)) == SECRET)
            for actor in ('student_b','teacher_b'):
                for route in ('queryById','queryTeachingWorkCorrectByMainId'):
                    denied(actor + ' cross-class business ' + route, 'GET', '/teaching/teachingWork/' + route + '?id=' + WORK, actor)
            for actor in ('student_a','teacher_a'):
                result = allowed(actor + ' legitimate feedback read', 'GET', '/teaching/teachingWork/queryTeachingWorkCorrectByMainId?id=' + WORK, actor)
                check(actor + ' receives the committed feedback', SECRET in json.dumps(result))
            for version in ('v1','v2'):
                insert('sys_data_log', id=PREFIX+version, data_table='teaching_work', data_id=WORK, data_version=version[1:],
                       data_content=json.dumps({'workId':WORK,'score':4,'comment':SECRET}), create_by='fixture_student_a')

            if args.expect_legacy:
                audit_id = sql('SELECT id FROM sys_log WHERE request_param LIKE ' + literal('%'+SECRET+'%') + ' ORDER BY id LIMIT 1')
                check('baseline actual grading aspect retained private DTO in audit', bool(audit_id))
                for actor in ('student_b','teacher_b'):
                    for route in history_reads(audit_id):
                        result = allowed(actor + ' baseline raw history route ' + route.split('?')[0], 'GET', route, actor)
                        check(actor + ' baseline history exposes the same private feedback', SECRET in json.dumps(result))
                allowed('baseline ordinary account deletes one audit row', 'DELETE', '/sys/log/delete?id='+audit_id, 'student_b')
                check('baseline unauthorized single delete persisted', sql('SELECT COUNT(*) FROM sys_log WHERE id='+literal(audit_id)) == '0')
                first, second = audit('delete1'), audit('delete2')
                allowed('baseline ordinary account batch deletes audit rows', 'DELETE', '/sys/log/deleteBatch?ids='+first+','+second, 'teacher_b')
                check('baseline unauthorized batch delete persisted', sql('SELECT COUNT(*) FROM sys_log WHERE id IN ('+literal(first)+','+literal(second)+')') == '0')
                audit('allclear')
                allowed('baseline ordinary account clears every audit row', 'DELETE', '/sys/log/deleteBatch?ids=allclear', 'student_b')
                check('baseline unauthorized allclear persisted', sql('SELECT COUNT(*) FROM sys_log') == '0')
            else:
                # Existing installations retain old DTO-bearing rows even after logging is minimized.
                audit_id = audit('historical')
                reads = history_reads(audit_id)
                deletes = ['/sys/log/delete?id='+audit_id, '/sys/log/deleteBatch?ids='+audit_id+','+audit_id,
                           '/sys/log/deleteBatch?ids=allclear']
                for actor in (None,'student_a','student_b','teacher_a','teacher_b'):
                    for route in reads:
                        denied(str(actor)+' audit read '+route.split('?')[0], 'GET', route, actor)
                    for route in deletes:
                        denied(str(actor)+' audit delete '+route, 'DELETE', route, actor)
                for route in reads:
                    result = allowed('administrator keeps historical management '+route.split('?')[0], 'GET', route)
                    check('administrator reads retained historical private marker', SECRET in json.dumps(result))
                dev_id = sql("SELECT id FROM sys_role WHERE role_code='dev' LIMIT 1")
                if not dev_id:
                    dev_id = PREFIX+'dev'
                    insert('sys_role',id=dev_id,role_code='dev',role_name='synthetic audit developer',role_level=0)
                insert('sys_user_role',id=PREFIX+'grant',user_id='fixture_student_b',role_id=dev_id)
                for route in reads:
                    result = allowed('same token with live developer grant '+route.split('?')[0], 'GET', route, 'student_b')
                    check('authorized developer reads historical marker', SECRET in json.dumps(result))
                sql('DELETE FROM sys_user_role WHERE id='+literal(PREFIX+'grant'))
                for route in reads:
                    denied('same token after live developer revocation '+route.split('?')[0], 'GET', route, 'student_b')
                for route in deletes:
                    denied('same token after live developer revocation '+route, 'DELETE', route, 'student_b')
                for route in ('/sys/log/queryById?id='+audit_id, '/sys/log/exportXls',
                              '/sys/dataLog/queryById?id='+PREFIX+'v1', '/sys/dataLog/exportXls'):
                    status, result = call('GET',route)
                    check('no unreviewed inherited detail/export route '+route.split('?')[0], status == 404 and SECRET not in json.dumps(result))
                allowed('administrator single deletion remains available', 'DELETE', '/sys/log/delete?id='+audit_id)
                check('authorized single deletion persisted', sql('SELECT COUNT(*) FROM sys_log WHERE id='+literal(audit_id)) == '0')
                first, second = audit('delete1'), audit('delete2')
                allowed('administrator batch deletion remains available', 'DELETE', '/sys/log/deleteBatch?ids='+first+','+second)
                check('authorized batch deletion persisted', sql('SELECT COUNT(*) FROM sys_log WHERE id IN ('+literal(first)+','+literal(second)+')') == '0')
                audit('allclear')
                allowed('administrator allclear remains available', 'DELETE', '/sys/log/deleteBatch?ids=allclear')
                check('authorized allclear persisted', sql('SELECT COUNT(*) FROM sys_log') == '0')
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            # Logout itself writes audit rows; close before restoring the complete prior table.
            api.close()
            sql('DELETE FROM sys_user_role WHERE id='+literal(PREFIX+'grant'))
            sql('DELETE FROM sys_role WHERE id='+literal(PREFIX+'dev'))
            for table in ('teaching_work_correct','teaching_work_comment','teaching_work_event'):
                sql('DELETE FROM '+table+' WHERE work_id='+literal(WORK))
            sql('DELETE FROM teaching_work WHERE id='+literal(WORK))
            sql('DELETE FROM sys_data_log WHERE data_id='+literal(WORK))
            restore('teaching_depart_day_log',original_daily)
            restore('sys_log',original_audit)
            check('all original audit history work feedback statistics and role rows restored', digest() == original)
        result = {'status':'passed' if error is None and all(c['passed'] for c in cases) else 'failed',
                  'cases':cases,'passed':sum(c['passed'] for c in cases),'failed':sum(not c['passed'] for c in cases),'total':len(cases),
                  'expected_legacy':bool(args.expect_legacy),'jar_sha256':api.jar_sha256,'exception':error,
                  'scope':'Exclusive synthetic HTTP/MySQL; actual grading, retained historical DTOs, role grant/revocation and full log restoration; no production'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result['status'] == 'passed'


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','jar','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expect-legacy',action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
