#!/usr/bin/env python3
"""Exercise student submission ownership, task scopes and protected fields."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_sprobe_'
NAME = 'submission-probe-'
BASE = '/teaching/teachingWork/'
TRIGGER = 'fixture_submission_failure'
TABLES = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_data_log',
          'teaching_additional_work', 'teaching_course_unit', 'teaching_course', 'teaching_course_dept',
          'sys_file', 'sys_user_depart', 'teaching_depart_day_log')


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def check(name, passed):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def file_snapshot():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        def cache_snapshot():
            return {key: set(api.cache('SMEMBERS', key).splitlines()) for key in cache_keys}

        def payload(suffix, **extra):
            return dict(workName=NAME + suffix, workType='2', workStatus='1', workFile=PREFIX + 'file_a', **extra)

        def submit(body, actor='student_a'):
            return api.request('POST', BASE + 'submit', actor, body)[:2]

        def allowed(name, body, actor='student_a'):
            status, result = submit(body, actor)
            ok = status == 200 and result and result.get('success') is True
            check(name, ok)
            return (result or {}).get('result') or {}

        def denied(name, body, actor='student_a', code=510):
            before, before_files, before_cache = snapshot(), file_snapshot(), cache_snapshot()
            status, result = submit(body, actor)
            check(name, status == (200 if actor else 401) and result and result.get('success') is False
                  and result.get('code') == (code if actor else 401) and not result.get('result'))
            check(name + ' preserves rows files and submission cache', snapshot() == before and file_snapshot() == before_files and cache_snapshot() == before_cache)

        def row(ident):
            fields = ('id', 'user_id', 'depart_id', 'course_id', 'additional_id', 'work_scene', 'work_name', 'work_type',
                      'work_status', 'work_file', 'work_cover', 'create_by', 'create_time', 'update_by', 'sys_org_code',
                      'view_num', 'star_num', 'collect_num', 'del_flag')
            value = sql('SELECT JSON_OBJECT(' + ','.join("'" + field + "'," + field for field in fields) + ") FROM teaching_work WHERE id='" + ident + "'")
            return json.loads(value) if value else {}

        def work(suffix, owner='fixture_student_a', course='', status=0, file_id=None):
            ident = PREFIX + suffix
            file_id = file_id or PREFIX + 'file_a'
            sql("INSERT INTO teaching_work (id,user_id,depart_id,course_id,work_name,work_type,work_file,work_status,create_by,create_time,view_num,star_num,collect_num) VALUES ('" + ident + "','" + owner + "','fixture_class_a','" + course + "','" + NAME + suffix + "','2','" + file_id + "'," + str(status) + ",'fixture_student_a','2026-01-01 00:00:00',7,8,9)")
            return ident

        original, original_files = snapshot(), file_snapshot()
        cache_keys = ['departLog:' + kind + ':fixture_class_' + side for kind in ('addiWorkSubmit', 'courseWorkSubmit') for side in ('a', 'b')]
        original_cache = cache_snapshot()
        if sql('SELECT COUNT(*) FROM teaching_depart_day_log') != '0':
            raise RuntimeError('This verifier needs the unused synthetic daily-log fixture')
        if any(sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != '0' for table in TABLES):
            raise RuntimeError('Existing submission probe rows')
        if sql("SELECT COUNT(*) FROM teaching_work WHERE work_name LIKE '" + NAME + "%'") != '0' or list((api.runtime / 'uploads').glob(NAME + '*')):
            raise RuntimeError('Existing submission probe work or files')
        if sql("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + TRIGGER + "'") != '0':
            raise RuntimeError('Existing submission failure trigger')
        trigger_created = False
        owned_paths = []
        try:
            for actor in ('student_a', 'student_b', 'teacher_a', 'admin'):
                api.login(actor)
            for side in ('a', 'b'):
                path = api.runtime / ('uploads/' + NAME + side + '.txt')
                path.write_text('synthetic submission ' + side)
                owned_paths.append(path)
                sql("INSERT INTO sys_file (id,file_name,file_path,file_location,create_by) VALUES ('" + PREFIX + "file_" + side + "','" + path.name + "','" + path.name + "',1,'fixture_student_" + side + "')")
                sql("INSERT INTO teaching_course_unit (id,course_id,unit_name,course_work_type) VALUES ('" + PREFIX + "unit_" + side + "','fixture_course_" + side + "','" + NAME + side + "',2)")
            for suffix, departments, state in [('a', 'fixture_class_a', 1), ('b', 'fixture_class_b', 1),
                                                 ('unpublished', 'fixture_class_a', 0), ('ended', 'fixture_class_a', 2),
                                                 ('multi', ' fixture_class_b , fixture_class_a ', 1),
                                                 ('substring', 'fixture_class_a_extra', 1), ('empty', '', 1)]:
                sql("INSERT INTO teaching_additional_work (id,work_name,work_dept,status,code_type) VALUES ('" + PREFIX + "addi_" + suffix + "','" + NAME + suffix + "','" + departments + "'," + str(state) + ",2)")
            own = work('existing', course=PREFIX + 'unit_a')
            foreign = work('foreign', owner='fixture_student_b', file_id=PREFIX + 'file_b')

            if args.expect_legacy:
                forged = payload('forged', userId='fixture_student_b', departId='fixture_class_b', createBy='fixture_admin',
                                 createTime='2001-01-01 00:00:00', viewNum=777, starNum=888, collectNum=999, delFlag=1, sysOrgCode='forged', workScene='exam')
                forged['workStatus'] = '4'
                result = allowed('legacy accepts protected fields and publication status', forged)
                stored = row(result['id'])
                check('legacy forged metadata and counters persist', stored['work_status'] == 4 and stored['create_by'] == 'fixture_admin' and stored['view_num'] == 777 and stored['depart_id'] == 'fixture_class_b')
                for suffix, body in [('course', payload('foreign_course', courseId=PREFIX + 'unit_b')),
                                     ('assignment', payload('foreign_assignment', additionalId=PREFIX + 'addi_b')),
                                     ('unpublished', payload('unpublished', additionalId=PREFIX + 'addi_unpublished')),
                                     ('ended', payload('ended', additionalId=PREFIX + 'addi_ended')),
                                     ('foreign_id', payload('foreign_id', id=foreign)),
                                     ('missing_id', payload('missing_id', id=PREFIX + 'missing')),
                                     ('foreign_file', dict(payload('foreign_file'), workFile=PREFIX + 'file_b'))]:
                    allowed('legacy accepts ' + suffix, body)
                before_identity = row(own)
                allowed('legacy owner can rebind assignment', payload('rebound', id=own, courseId=PREFIX + 'unit_b'))
                check('legacy task identity and creation time changed', row(own)['course_id'] != before_identity['course_id'] and row(own)['create_time'] != before_identity['create_time'])
                draft = payload('draft', courseId=PREFIX + 'unit_a'); draft['workStatus'] = '0'
                allowed('legacy draft save', draft)
                check('legacy draft counted as a course submission', int(sql("SELECT COALESCE(SUM(course_work_submit_count),0) FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'")) > 0)
            else:
                denied('anonymous submission rejected', payload('anonymous'), actor=None)
                for actor in ('student_a', 'teacher_a', 'admin'):
                    denied(actor + ' cannot submit another owner ID', payload('foreign_id', id=foreign), actor)
                denied('missing explicit ID cannot become a new work', payload('missing', id=PREFIX + 'missing'))
                denied('other class course rejected', payload('course_b', courseId=PREFIX + 'unit_b'))
                denied('missing course unit rejected', payload('missing_unit', courseId=PREFIX + 'no_unit'))
                for suffix in ('b', 'unpublished', 'ended', 'substring', 'empty', 'missing'):
                    denied('assignment ' + suffix + ' rejected', payload('addi_' + suffix, additionalId=PREFIX + 'addi_' + suffix))
                denied('mixed task identities rejected', payload('both', courseId=PREFIX + 'unit_a', additionalId=PREFIX + 'addi_a'), code=500)
                denied('owner cannot rebind task', payload('rebind', id=own, courseId=PREFIX + 'unit_b'))
                denied('owner cannot add a second task', payload('rebind_addi', id=own, additionalId=PREFIX + 'addi_a'))
                for state in ('2', '3', '4', '-1', '99'):
                    denied('student cannot set status ' + state, dict(payload('state'), workStatus=state), code=500)
                denied('new foreign file rejected', dict(payload('file_b'), workFile=PREFIX + 'file_b'))
                denied('foreign cover rejected', payload('cover_b', workCover=PREFIX + 'file_b'))
                denied('unregistered file rejected', dict(payload('file_missing'), workFile=PREFIX + 'no_file'))

                forged = payload('protected', userId='fixture_student_b', departId='fixture_class_b', createBy='fixture_admin',
                                 createTime='2001-01-01 00:00:00', updateBy='fixture_admin', updateTime='2001-01-01 00:00:00',
                                 viewNum=777, starNum=888, collectNum=999, delFlag=1, sysOrgCode='forged', workScene='exam')
                result = allowed('personal creation ignores protected fields', forged)
                stored = row(result['id'])
                check('new owner audit fields and counters are server controlled', stored['user_id'] == 'fixture_student_a' and stored['create_by'] == 'fixture_student_a'
                      and not stored['create_time'].startswith('2001') and stored['view_num'] == stored['star_num'] == stored['collect_num'] == stored['del_flag'] == 0
                      and stored['depart_id'] == '' and stored['sys_org_code'] != 'forged' and stored['update_by'] is None and stored['work_scene'] == 'create')

                before_identity = row(own)
                update = dict(forged, id=own, workName=NAME + 'existing_updated', workStatus='0')
                result = allowed('owner saves course draft with spoofed metadata', update)
                stored = row(own)
                immutable = ('id', 'user_id', 'depart_id', 'course_id', 'additional_id', 'create_by', 'create_time', 'sys_org_code', 'view_num', 'star_num', 'collect_num', 'del_flag')
                check('existing identity audit origin and counters preserved', all(stored[k] == before_identity[k] for k in immutable) and stored['update_by'] == 'fixture_student_a' and stored['work_status'] == 0)
                check('draft does not increment daily submission or reserve cache', sql('SELECT COUNT(*) FROM teaching_depart_day_log') == '0' and cache_snapshot() == original_cache)
                history = json.loads(sql("SELECT data_content FROM sys_data_log WHERE data_id='" + own + "' ORDER BY data_version DESC LIMIT 1"))
                check('history records actual previous version', history['workName'] == before_identity['work_name'] and history['createBy'] == before_identity['create_by'] and history['viewNum'] == 7)
                result = allowed('course submit with omitted task fields retains original task', payload('course_submit', id=own, departId='fixture_class_b'))
                check('server resolves course class and submitted status', result['id'] == own and result['courseId'] == PREFIX + 'unit_a' and result['departId'] == 'fixture_class_a' and result['workStatus'] == '1')
                allowed('retry without work ID updates same assigned work', payload('course_retry', courseId=PREFIX + 'unit_a'))
                check('sequential retry keeps one course work and one submission count', sql("SELECT COUNT(*) FROM teaching_work WHERE user_id='fixture_student_a' AND course_id='" + PREFIX + "unit_a'") == '1'
                      and sql("SELECT SUM(course_work_submit_count) FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'") == '1')

                for kind in ('2', '3', '4', '0'):
                    allowed('editor/file payload type ' + kind, dict(payload('type_' + kind), workType=kind))
                new_assignment = allowed('file modal payload submits assigned work', dict(payload('file_modal', additionalId=PREFIX + 'addi_a', departId='fixture_class_b'), workType='0'))
                check('assignment class and scene are derived', new_assignment['departId'] == 'fixture_class_a' and new_assignment['workScene'] == 'additional' and new_assignment['workStatus'] == '1')
                sql("INSERT INTO sys_user_depart (id,user_id,dep_id) VALUES ('" + PREFIX + "membership','fixture_student_a','fixture_class_b')")
                multi = allowed('choose an eligible class on a multi-class assignment', payload('multi', additionalId=PREFIX + 'addi_multi', departId='fixture_class_b'))
                check('eligible selected class stored', multi['departId'] == 'fixture_class_b')
                retry = allowed('multi-class retry cannot transfer existing work', payload('multi_retry', additionalId=PREFIX + 'addi_multi', departId='fixture_class_a'))
                check('existing assignment class remains stable', retry['id'] == multi['id'] and retry['departId'] == 'fixture_class_b')
                sql("DELETE FROM sys_user_depart WHERE id='" + PREFIX + "membership'")
                denied('revoked assignment membership prevents later update', payload('revoked', id=multi['id']))

                sql("INSERT INTO teaching_course (id,course_name,is_shared) VALUES ('" + PREFIX + "shared','" + NAME + "shared',1)")
                sql("INSERT INTO teaching_course_unit (id,course_id,unit_name) VALUES ('" + PREFIX + "shared_unit','" + PREFIX + "shared','" + NAME + "shared')")
                shared = allowed('unassigned shared course accepts personal practice', payload('shared', courseId=PREFIX + 'shared_unit', departId='fixture_class_b'))
                check('shared practice does not invent a class', shared['departId'] == '')
                sql("INSERT INTO teaching_course_dept (id,course_id,dept_id) VALUES ('" + PREFIX + "shared_binding','" + PREFIX + "shared','fixture_class_a')")
                bound_shared = work('bound_shared', course=PREFIX + 'shared_unit')
                allowed('class-bound shared work saves while assigned', payload('bound_shared_update', id=bound_shared))
                sql("DELETE FROM teaching_course_dept WHERE id='" + PREFIX + "shared_binding'")
                denied('shared visibility cannot bypass revoked class binding', payload('revoked_shared', id=bound_shared))
                sql("UPDATE teaching_course_unit SET del_flag=1 WHERE id='" + PREFIX + "shared_unit'")
                denied('deleted unit rejects submission', payload('deleted_unit', id=shared['id']))

                collision = work('collision', course=PREFIX + 'unit_b')
                free = allowed('personal name collision cannot overwrite course work', payload('collision'))
                check('course work identity survives personal-name collision', free['id'] != collision and row(collision)['course_id'] == PREFIX + 'unit_b')
                sent = work('sent', file_id=PREFIX + 'file_b')
                result = allowed('owned sent copy can retain shared source attachment', dict(payload('sent_update', id=sent), workFile=PREFIX + 'file_b'))
                check('legitimate shared attachment preserved', result['workFile'] == PREFIX + 'file_b')

                status, reopened, _ = api.request('GET', BASE + 'queryById?id=' + own, 'student_a')
                check('saved course work reopens through actual owner API', status == 200 and reopened.get('success') and reopened['result']['workFile'] == PREFIX + 'file_a')
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/' + owned_paths[0].name,
                                  headers={'X-Access-Token': api.tokens['student_a']})
                with urlopen(request, timeout=15) as response:
                    check('reopened attachment exact HTTP bytes', response.status == 200 and response.read() == owned_paths[0].read_bytes())

                # Force UPDATE failure after the service has attempted its history
                # insert. Both must roll back, with no submission cache side effect.
                before, before_cache = snapshot(), cache_snapshot()
                sql("DELIMITER //\nCREATE TRIGGER " + TRIGGER + " BEFORE UPDATE ON teaching_work FOR EACH ROW BEGIN IF OLD.id='" + own + "' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic submission failure'; END IF; END//\nDELIMITER ;")
                trigger_created = True
                status, result = submit(payload('failed_update', id=own))
                check('injected update failure reports failure', result and result.get('success') is False)
                check('storage error response contains no SQL diagnostics', result.get('message') == '作品保存失败，请稍后重试' and not result.get('result'))
                check('failed update rolls back work history metrics and cache', snapshot() == before and cache_snapshot() == before_cache)
                sql('DROP TRIGGER ' + TRIGGER); trigger_created = False
                allowed('retry succeeds after database failure removed', payload('retried', id=own))

                sql("INSERT INTO teaching_course_unit (id,course_id,unit_name) VALUES ('" + PREFIX + "fault_unit','fixture_course_a','" + NAME + "fault')")
                before, before_cache = snapshot(), cache_snapshot()
                sql("DELIMITER //\nCREATE TRIGGER " + TRIGGER + " BEFORE UPDATE ON teaching_depart_day_log FOR EACH ROW BEGIN IF OLD.depart_id='fixture_class_a' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic daily record failure'; END IF; END//\nDELIMITER ;")
                trigger_created = True
                status, result = submit(payload('failed_daily', courseId=PREFIX + 'fault_unit'))
                check('daily-record failure reports failure instead of partial success', result and result.get('success') is False)
                check('daily-record error response contains no SQL diagnostics', result.get('message') == '作品保存失败，请稍后重试' and not result.get('result'))
                check('daily-record failure rolls back new work and leaves no cache reservation', snapshot() == before and cache_snapshot() == before_cache)
                sql('DROP TRIGGER ' + TRIGGER); trigger_created = False
                allowed('retry new submission after daily-record failure', payload('retried_daily', courseId=PREFIX + 'fault_unit'))
            jar_hash = api.jar_sha256
        finally:
            if trigger_created:
                sql('DROP TRIGGER ' + TRIGGER)
            sql("DELETE FROM sys_data_log WHERE data_table='teaching_work' AND data_id IN (SELECT id FROM teaching_work WHERE work_name LIKE '" + NAME + "%')")
            sql("DELETE FROM teaching_work WHERE work_name LIKE '" + NAME + "%'; DELETE FROM teaching_depart_day_log WHERE depart_id IN ('fixture_class_a','fixture_class_b')")
            for table in ('teaching_additional_work', 'teaching_course_unit', 'teaching_course_dept', 'teaching_course', 'sys_file', 'sys_user_depart'):
                sql("DELETE FROM " + table + " WHERE id LIKE '" + PREFIX + "%'")
            for key, members in cache_snapshot().items():
                for member in members - original_cache[key]:
                    api.cache('SREM', key, member)
            for path in owned_paths:
                path.unlink(missing_ok=True)
        check('all original business and history rows restored', snapshot() == original)
        check('all original file bytes restored', file_snapshot() == original_files)
        check('all original submission cache memberships restored', cache_snapshot() == original_cache)
        check('temporary database failure trigger removed', sql("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + TRIGGER + "'") == '0')
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash, 'expected_legacy': args.expect_legacy,
              'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases,
              'scope': 'actual synthetic HTTP submission and re-read, DB/history/cache/files; editor-shaped payloads are not browser editor acceptance; no concurrency or global file-API acceptance'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
