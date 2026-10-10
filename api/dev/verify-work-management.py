#!/usr/bin/env python3
"""Exercise work-management ownership and class boundaries on synthetic fixtures."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_wprobe_'
BASE = '/teaching/teachingWork/'
TABLES = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_file',
          'sys_user_depart', 'sys_depart', 'sys_role', 'sys_user_role', 'teaching_depart_day_log')


def verify(args):
    cases = []
    followups = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api, tempfile.TemporaryDirectory(prefix='work-check-', dir=args.runtime) as temp_dir:
        temp = Path(temp_dir)
        process = json.loads((api.runtime / 'backend-process.json').read_text())
        with zipfile.ZipFile(process['jar_path']) as jar:
            names = [name for name in jar.namelist() if re.fullmatch(r'BOOT-INF/lib/poi-[0-9.]+\.jar', name)]
            if len(names) != 1:
                raise RuntimeError('Expected one application POI core dependency')
            (temp / 'poi.jar').write_bytes(jar.read(names[0]))
        java = args.java_home.resolve() / 'bin/java'
        subprocess.run([str(java.with_name('javac')), '-cp', str(temp / 'poi.jar'), '-d', str(temp),
                        str(Path(__file__).with_name('ReadXlsCells.java'))], check=True, capture_output=True)

        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def files():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        def check(name, passed):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def call(method, path, actor=None, data=None):
            if not path.startswith(('exportXls', 'importExcel')):
                return api.request(method, BASE + path, actor, data)[:2]
            headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
            body = None
            if path.startswith('importExcel'):
                headers['Content-Type'] = 'multipart/form-data; boundary=work-probe-boundary'
                body = b'--work-probe-boundary--\r\n'
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + BASE + path,
                              data=body, headers=headers, method=method)
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read()
                if raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
                    (temp / 'export.xls').write_bytes(raw)
                    output = subprocess.check_output([str(java), '-cp', str(temp) + ':' + str(temp / 'poi.jar'),
                                                       'ReadXlsCells', str(temp / 'export.xls')], text=True)
                    return response.status, {'xls': True, 'cells': {base64.b64decode(v).decode() for v in output.splitlines()}}
                try:
                    return response.status, json.loads(raw)
                except ValueError:
                    return response.status, None

        def allowed(name, method, path, actor, data=None):
            status, body = call(method, path, actor, data)
            check(name, status == 200 and body and (body.get('success') is True or body.get('xls') is True))
            return body or {}

        def denied(name, method, path, actor, data=None):
            status, body = call(method, path, actor, data)
            check(name, status == (200 if actor else 401) and body and body.get('success') is False
                  and body.get('code') == (510 if actor else 401) and not body.get('result'))

        def relogin(actor):
            api.request('GET', '/sys/logout', actor)
            api.login(actor)

        def work_body(suffix, owner='fixture_student_a', department='fixture_class_a'):
            return {'id': PREFIX + suffix, 'userId': owner, 'departId': department, 'workName': 'work-probe-' + suffix,
                    'workType': '1', 'workFile': '', 'workStatus': '0', 'teachingWorkCorrectList': [], 'teachingWorkCommentList': []}

        original, original_files = snapshot(), files()
        original_teacher_depart = sql("SELECT depart_ids FROM sys_user WHERE id='fixture_teacher_a'")
        if original_teacher_depart != 'fixture_class_a' or sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'") != 'fixture_role_admin':
            raise RuntimeError('Unexpected synthetic account state')
        for table in TABLES:
            if sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != '0':
                raise RuntimeError('Existing probe rows; refusing overwrite')
        if sql("SELECT COUNT(*) FROM teaching_work WHERE work_name LIKE 'work-probe-%'") != '0':
            raise RuntimeError('Existing probe work names; refusing overwrite')
        for side in ('a', 'b'):
            if (api.runtime / ('uploads/work-probe-' + side + '.txt')).exists():
                raise RuntimeError('Existing probe attachment')
        try:
            for actor in ('admin', 'student_a', 'student_b', 'teacher_a', 'teacher_b'):
                api.login(actor)
            # Student A attends both classes, but a class-bound work belongs to one.
            sql("INSERT INTO sys_user_depart (id,user_id,dep_id) VALUES ('" + PREFIX + "membership','fixture_student_a','fixture_class_b')")
            sql("INSERT INTO sys_depart (id,parent_id,depart_name,org_code,org_type,org_category,del_flag,status) VALUES ('" + PREFIX + "child','fixture_class_a','probe child','A99A01A01','3','3','0','1')")
            samples = {'a': ('fixture_student_a', 'fixture_class_a'), 'b': ('fixture_student_b', 'fixture_class_b'),
                       'multi': ('fixture_student_a', 'fixture_class_b'), 'free': ('fixture_student_a', ''),
                       'wrong': ('fixture_student_b', 'fixture_class_a'), 'child': ('fixture_student_a', PREFIX + 'child')}
            for suffix, (owner, department) in samples.items():
                file_id = PREFIX + 'file_' + suffix if suffix in ('a', 'b') else ''
                sql("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_type,work_file,work_status,create_by,create_time) VALUES ('" + PREFIX + suffix + "','" + owner + "','" + department + "','work-probe-" + suffix + "','1','" + file_id + "',0,'fixture_student_a','2026-10-03 00:00:00')")
                if file_id:
                    (api.runtime / ('uploads/work-probe-' + suffix + '.txt')).write_text('work probe ' + suffix)
                    sql("INSERT INTO sys_file (id,file_name,file_path,file_location) VALUES ('" + file_id + "','work-probe-" + suffix + ".txt','work-probe-" + suffix + ".txt',1)")
            for table, extra_columns, extra_values in [('teaching_work_correct', 'score,comment', "3,'private feedback'"),
                                                        ('teaching_work_comment', 'user_id,comment', "'fixture_student_a','private comment'")]:
                for suffix in ('a', 'b'):
                    sql("INSERT INTO " + table + " (id,work_id," + extra_columns + ") VALUES ('" + PREFIX + table.rsplit('_', 1)[1] + suffix + "','" + PREFIX + suffix + "'," + extra_values + ")")

            if args.expect_legacy:
                allowed('student reads another owner work before fix', 'GET', 'queryById?id=' + PREFIX + 'b', 'student_a')
                allowed('teacher reads other class feedback before fix', 'GET', 'queryTeachingWorkCorrectByMainId?id=' + PREFIX + 'b', 'teacher_a')
                allowed('student edits other work before fix', 'PUT', 'edit', 'student_a', {'id': PREFIX + 'b', 'workName': 'work-probe-changed'})
                check('unauthorized student write persisted', sql("SELECT work_name FROM teaching_work WHERE id='" + PREFIX + "b'") == 'work-probe-changed')
                rows = allowed('teacher list before fix', 'GET', 'list?pageSize=50', 'teacher_a').get('result', {}).get('records', [])
                check('multi-class owner leaks class B work into teacher A list before fix', PREFIX + 'multi' in {row['id'] for row in rows})
                cells = allowed('teacher export before fix', 'GET', 'exportXls', 'teacher_a').get('cells', set())
                check('teacher export leaks other owner class B work before fix', 'work-probe-changed' in cells)
                allowed('teacher deletes other class work before fix', 'DELETE', 'delete?id=' + PREFIX + 'b', 'teacher_a')
                check('unauthorized deletion removed work and attachment', sql("SELECT COUNT(*) FROM teaching_work WHERE id='" + PREFIX + "b'") == '0' and not (api.runtime / 'uploads/work-probe-b.txt').exists())
            else:
                protected = [('GET', 'list', None), ('POST', 'add', work_body('denied')),
                             ('PUT', 'edit', {'id': PREFIX + 'b', 'workName': 'work-probe-denied'}),
                             ('DELETE', 'delete?id=' + PREFIX + 'b', None),
                             ('DELETE', 'deleteBatch?ids=' + PREFIX + 'a,' + PREFIX + 'b', None),
                             ('POST', 'sendWork', {'sendWorkId': PREFIX + 'a', 'userIdList': ['fixture_teacher_a']}),
                             ('GET', 'exportXls', None), ('POST', 'importExcel', None)]
                denial_snapshot, denial_files = snapshot(), files()
                for actor in (None, 'student_a', 'student_b'):
                    for method, path, body in protected:
                        denied((actor or 'anonymous') + ' management ' + path.split('?')[0], method, path, actor, body)
                    check((actor or 'anonymous') + ' denied management preserves rows and files', snapshot() == denial_snapshot and files() == denial_files)
                read_routes = ('queryById', 'queryTeachingWorkCorrectByMainId', 'queryTeachingWorkCommentByMainId')
                for route in read_routes:
                    denied('anonymous private ' + route, 'GET', route + '?id=' + PREFIX + 'a', None)
                    denied('other student private ' + route, 'GET', route + '?id=' + PREFIX + 'b', 'student_a')
                    denied('other class teacher private ' + route, 'GET', route + '?id=' + PREFIX + 'a', 'teacher_b')
                    for actor in ('student_a', 'teacher_a', 'admin'):
                        allowed(actor + ' authorized private ' + route, 'GET', route + '?id=' + PREFIX + 'a', actor)
                for suffix in ('b', 'multi', 'wrong'):
                    denied('teacher A cannot read out-of-scope ' + suffix, 'GET', 'queryById?id=' + PREFIX + suffix, 'teacher_a')
                    denied('teacher A cannot edit out-of-scope ' + suffix, 'PUT', 'edit', 'teacher_a', {'id': PREFIX + suffix, 'workName': 'work-probe-denied'})
                    denied('teacher A cannot delete out-of-scope ' + suffix, 'DELETE', 'delete?id=' + PREFIX + suffix, 'teacher_a')
                denied('teacher cannot create cross-class owner', 'POST', 'add', 'teacher_a', work_body('denied', 'fixture_student_b', 'fixture_class_b'))
                denied('teacher cannot import unscoped workbook', 'POST', 'importExcel', 'teacher_a')
                denied('mixed class delete rejected before first mutation', 'DELETE', 'deleteBatch?ids=' + PREFIX + 'a,' + PREFIX + 'b', 'teacher_a')
                denied('mixed recipients rejected before first write', 'POST', 'sendWork', 'teacher_a', {'sendWorkId': PREFIX + 'a', 'userIdList': ['fixture_teacher_a', 'fixture_student_b']})
                denied('foreign source cannot be sent to own class', 'POST', 'sendWork', 'teacher_a', {'sendWorkId': PREFIX + 'b', 'userIdList': ['fixture_student_a']})
                check('all resource denials preserve business rows and attachment bytes', snapshot() == denial_snapshot and files() == denial_files)

                for actor, present, absent in [('teacher_a', {'a', 'free', 'child'}, {'b', 'multi', 'wrong'}),
                                                ('teacher_b', {'b', 'multi', 'free'}, {'a', 'wrong', 'child'}),
                                                ('admin', set(samples), set())]:
                    rows = allowed(actor + ' scoped list', 'GET', 'list?pageSize=50', actor).get('result', {}).get('records', [])
                    ids = {row['id'] for row in rows}
                    check(actor + ' list applies class and owner boundary', all(PREFIX + v in ids for v in present) and not any(PREFIX + v in ids for v in absent))
                    cells = allowed(actor + ' scoped XLS export', 'GET', 'exportXls', actor).get('cells', set())
                    check(actor + ' decoded XLS cells match class boundary', all('work-probe-' + v in cells for v in present) and not any('work-probe-' + v in cells for v in absent))
                cells = allowed('foreign-only export selection produces no foreign work', 'GET', 'exportXls?selections=' + PREFIX + 'b,' + PREFIX + 'multi,' + PREFIX + 'wrong', 'teacher_a').get('cells', set())
                check('selections cannot bypass export scope', not any('work-probe-' + v in cells for v in samples))
                rows = allowed('foreign department filter stays within teacher scope', 'GET', 'list?departId=fixture_class_b&pageSize=50', 'teacher_a').get('result', {}).get('records', [])
                check('foreign filter does not expose class B rows', not any(row.get('departId') == 'fixture_class_b' for row in rows))
                allowed('teacher reads descendant-class work', 'GET', 'queryById?id=' + PREFIX + 'child', 'teacher_a')
                allowed('owner reads own work in second class', 'GET', 'queryById?id=' + PREFIX + 'multi', 'student_a')

                # Confirm teacher feedback cannot reassign the resource, even when the
                # request carries a different owner, class and assignment.
                identity = sql("SELECT CONCAT_WS('|',user_id,depart_id,COALESCE(course_id,'NULL'),additional_id,create_by,create_time) FROM teaching_work WHERE id='" + PREFIX + "a'")
                allowed('teacher feedback allowed for own class', 'PUT', 'edit', 'teacher_a', {
                    'id': PREFIX + 'a', 'userId': 'fixture_student_b', 'departId': 'fixture_class_b',
                    'courseId': 'fixture_unit_b', 'additionalId': 'fixture_additional_b', 'createBy': 'fixture_admin',
                    'createTime': '2000-01-01 00:00:00', 'workStatus': '2',
                    'teachingWorkCorrectList': [{'score': 4, 'comment': 'authorized feedback'}],
                    'teachingWorkCommentList': [{'userId': 'fixture_teacher_a', 'comment': 'authorized comment'}]})
                check('feedback preserves original owner class assignment and creator', sql("SELECT CONCAT_WS('|',user_id,depart_id,COALESCE(course_id,'NULL'),additional_id,create_by,create_time) FROM teaching_work WHERE id='" + PREFIX + "a'") == identity)
                check('feedback and comment persisted', sql("SELECT CONCAT(score,':',comment) FROM teaching_work_correct WHERE work_id='" + PREFIX + "a'") == '4:authorized feedback' and sql("SELECT comment FROM teaching_work_comment WHERE work_id='" + PREFIX + "a'") == 'authorized comment')
                feedback = allowed('owner reads saved feedback', 'GET', 'queryTeachingWorkCorrectByMainId?id=' + PREFIX + 'a', 'student_a').get('result', [])
                check('owner receives actual saved score and comment', any(v.get('score') == 4 and v.get('comment') == 'authorized feedback' for v in feedback))
                allowed('teacher sends to authorized class member', 'POST', 'sendWork', 'teacher_a', {'sendWorkId': PREFIX + 'a', 'userIdList': ['fixture_teacher_a']})
                check('authorized send persists target owner', sql("SELECT COUNT(*) FROM teaching_work WHERE work_name='work-probe-a' AND user_id='fixture_teacher_a'") == '1')
                sql("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_type,work_file,create_by,create_time) VALUES ('" + PREFIX + "collision','fixture_student_a','fixture_class_b','work-probe-a','1','','fixture_student_a','2026-10-03 00:00:00')")
                collision_before = snapshot()
                denied('same-name overwrite outside teacher class denied', 'POST', 'sendWork', 'teacher_a', {'sendWorkId': PREFIX + 'a', 'userIdList': ['fixture_student_a']})
                check('denied send preserves every potential overwrite target', snapshot() == collision_before)

                for actor in ('teacher_a', 'admin', 'dev'):
                    request_actor = 'admin' if actor == 'dev' else actor
                    if actor == 'dev':
                        sql("INSERT INTO sys_role (id,role_code,role_name) VALUES ('" + PREFIX + "dev','dev','work probe dev'); UPDATE sys_user_role SET role_id='" + PREFIX + "dev' WHERE id='role_fixture_admin'")
                        relogin('admin')
                    body = work_body('crud_' + actor, 'fixture_student_a' if actor == 'teacher_a' else 'fixture_student_b', 'fixture_class_a' if actor == 'teacher_a' else 'fixture_class_b')
                    allowed(actor + ' creates managed work', 'POST', 'add', request_actor, body)
                    check(actor + ' create persisted', sql("SELECT COUNT(*) FROM teaching_work WHERE id='" + body['id'] + "'") == '1')
                    allowed(actor + ' edits managed work', 'PUT', 'edit', request_actor, {'id': body['id'], 'workName': 'work-probe-updated-' + actor})
                    check(actor + ' edit persisted', sql("SELECT work_name FROM teaching_work WHERE id='" + body['id'] + "'") == 'work-probe-updated-' + actor)
                    allowed(actor + ' reads managed work', 'GET', 'queryById?id=' + body['id'], request_actor)
                    allowed(actor + ' deletes managed work', 'DELETE', 'delete?id=' + body['id'], request_actor)
                    check(actor + ' delete persisted', sql("SELECT COUNT(*) FROM teaching_work WHERE id='" + body['id'] + "'") == '0')
                    allowed(actor + ' recreates for batch delete', 'POST', 'add', request_actor, body)
                    allowed(actor + ' batch deletes managed work', 'DELETE', 'deleteBatch?ids=' + body['id'], request_actor)
                    check(actor + ' batch delete persisted', sql("SELECT COUNT(*) FROM teaching_work WHERE id='" + body['id'] + "'") == '0')
                    if actor != 'teacher_a':
                        allowed(actor + ' empty import reaches existing validation', 'POST', 'importExcel', request_actor)
                        allowed(actor + ' management list available', 'GET', 'list', request_actor)
                        allowed(actor + ' export available', 'GET', 'exportXls', request_actor)
                sql("UPDATE sys_user SET depart_ids='' WHERE id='fixture_teacher_a'")
                relogin('teacher_a')
                for path in ('list', 'exportXls', 'queryById?id=' + PREFIX + 'a'):
                    denied('teacher without managed classes denied ' + path.split('?')[0], 'GET', path, 'teacher_a')
                sql("UPDATE sys_user SET depart_ids='fixture_class_a' WHERE id='fixture_teacher_a'")
                relogin('teacher_a')
                allowed('teacher deletes own probe attachment', 'DELETE', 'delete?id=' + PREFIX + 'a', 'teacher_a')
                check('allowed deletion removes owned work and child rows', sql("SELECT COUNT(*) FROM teaching_work WHERE id='" + PREFIX + "a'") == '0' and sql("SELECT COUNT(*) FROM teaching_work_correct WHERE work_id='" + PREFIX + "a'") == '0')
                check('unrelated class attachment retained', (api.runtime / 'uploads/work-probe-b.txt').read_text() == 'work probe b')
                followups.append({'issue': 'Deleting a sent source may remove the recipient shared attachment',
                                  'recipient_still_references_source_file': sql("SELECT COUNT(*) FROM teaching_work WHERE work_name='work-probe-a' AND user_id='fixture_teacher_a' AND work_file='" + PREFIX + "file_a'") == '1',
                                  'shared_attachment_missing': not (api.runtime / 'uploads/work-probe-a.txt').exists(),
                                  'status': 'observation on this candidate only; dedicated attachment-lifecycle checks cover preservation and reclamation'})
                allowed('teacher B deletes own unshared attachment', 'DELETE', 'delete?id=' + PREFIX + 'b', 'teacher_b')
                check('authorized unshared deletion removes attachment bytes and file row', not (api.runtime / 'uploads/work-probe-b.txt').exists() and sql("SELECT COUNT(*) FROM sys_file WHERE id='" + PREFIX + "file_b'") == '0')
            jar_hash = api.jar_sha256
        finally:
            for table in ('teaching_work_correct', 'teaching_work_comment'):
                sql("DELETE FROM " + table + " WHERE work_id IN (SELECT id FROM teaching_work WHERE work_name LIKE 'work-probe-%') OR id LIKE '" + PREFIX + "%'")
            sql("DELETE FROM teaching_work WHERE work_name LIKE 'work-probe-%' OR id LIKE '" + PREFIX + "%'; DELETE FROM sys_file WHERE id LIKE '" + PREFIX + "%'; DELETE FROM sys_user_depart WHERE id LIKE '" + PREFIX + "%'; DELETE FROM sys_depart WHERE id LIKE '" + PREFIX + "%'")
            sql("UPDATE sys_user_role SET role_id='fixture_role_admin' WHERE id='role_fixture_admin'; DELETE FROM sys_role WHERE id='" + PREFIX + "dev'; UPDATE sys_user SET depart_ids='fixture_class_a' WHERE id='fixture_teacher_a'")
            for side in ('a', 'b'):
                (api.runtime / ('uploads/work-probe-' + side + '.txt')).unlink(missing_ok=True)
            for actor in ('admin', 'teacher_a'):
                if actor in api.tokens:
                    api.request('GET', '/sys/logout', actor)
        check('all original business class role and daily-log rows restored', snapshot() == original)
        check('teacher managed class restored', sql("SELECT depart_ids FROM sys_user WHERE id='fixture_teacher_a'") == original_teacher_depart)
        check('all original attachment bytes restored', files() == original_files)
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash,
              'expected_legacy': args.expect_legacy, 'scope': 'actual synthetic HTTP/DB/files and decoded XLS cells; empty import gate only; no browser role or editor acceptance',
              'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases, 'known_followups': followups}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
