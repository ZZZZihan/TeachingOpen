#!/usr/bin/env python3
"""Verify live assignment read boundaries and retirement of the creator-only list."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command

BASE = '/teaching/teachingAdditionalWork/'
TABLES = ('teaching_additional_work', 'teaching_work', 'teaching_work_correct', 'teaching_work_comment',
          'sys_data_log', 'sys_file', 'teaching_course', 'teaching_course_dept', 'teaching_depart_day_log',
          'sys_user', 'sys_user_role', 'sys_user_depart', 'sys_role')
RETIRED_PATHS = ('teacherList', 'teacherList/', '%74eacherList', 'teacher%4cist',
                 'teacherList;legacy=1', 'TeacherList', 'teacherList.json')
MANAGEMENT_PATHS = ('list', 'list/', '%6cist', 'list;legacy=1')


def verify(args):
    if args.output.exists():
        raise RuntimeError('Refusing to overwrite an existing evidence report')
    cases, error = [], None
    expect_legacy_details = getattr(args, 'expect_legacy', False)
    expect_legacy_teacher_list = getattr(args, 'expect_legacy_teacher_list', False) or expect_legacy_details
    expect_legacy_management_list = getattr(args, 'expect_legacy_management_list', False)
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            output = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if output.returncode:
                raise RuntimeError('Owned additional-work read fixture SQL failed')
            return output.stdout.strip()

        def literal(value):
            return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)" if str(value) else "''"

        def insert(table, **values):
            sql('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES (' + ','.join(literal(v) for v in values.values()) + ')')

        def check(name, passed, fatal=True):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed and fatal:
                raise AssertionError(name)

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def file_snapshot():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        def cache_snapshot():
            # Sessions/CAPTCHAs are expected authentication activity. Compare all
            # other serialized values and key membership, not ticking TTLs.
            script = ("local values={}; for _,key in ipairs(redis.call('KEYS','*')) do "
                      "if string.sub(key,1,10)~='userToken:' and not "
                      "(string.len(key)==32 and string.match(key,'^[a-fA-F0-9]+$')) then "
                      "local value=redis.call('DUMP',key); if value then "
                      "table.insert(values,redis.sha1hex(key)..':'..redis.sha1hex(value)) end end end; "
                      "table.sort(values); return redis.sha1hex(table.concat(values,'|'))")
            digest = api.cache('EVAL', script, '0')
            if not re.fullmatch('[0-9a-f]{40}', digest):
                raise RuntimeError('Read-boundary cache snapshot returned an invalid digest')
            return digest

        def read_state():
            return snapshot(), cache_snapshot(), file_snapshot()

        def raw_get(path, actor):
            # Keep the raw body for disclosure checks, including non-JSON errors.
            headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + path, headers=headers)
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as failure:
                response = failure
            with response:
                return response.status, response.read().decode('utf-8', errors='replace')

        prefix = 'addi_read_' + uuid4().hex[:12]
        sentinel = 'private additional task ' + prefix
        original_rows, original_files = snapshot(), file_snapshot()
        task_suffixes = ('a', 'b', 'draft', 'multi', 'prefix', 'case', 'spaced', 'interior', 'unicode_space', 'unicode_line')
        task_ids = [prefix + '_' + suffix for suffix in task_suffixes]
        teacher_where = "user_id='fixture_teacher_a'"
        original_department = sql("SELECT IFNULL(HEX(depart_ids),'NULL') FROM sys_user WHERE id='fixture_teacher_a'")
        saved_roles = sql('SELECT HEX(id),HEX(user_id),HEX(role_id) FROM sys_user_role WHERE '
                          + teacher_where + ' ORDER BY id').splitlines()
        department_changed, roles_changed, fixtures_owned = False, False, False

        def restore_department():
            value = 'NULL' if original_department == 'NULL' else 'CONVERT(0x' + original_department + ' USING utf8mb4)'
            sql("UPDATE sys_user SET depart_ids=" + value + " WHERE id='fixture_teacher_a'")

        def restore_roles():
            sql('DELETE FROM sys_user_role WHERE ' + teacher_where)
            for row in saved_roles:
                values = row.split('\t')
                if len(values) != 3 or any(not re.fullmatch('[0-9A-Fa-f]+', value) for value in values):
                    raise RuntimeError('Invalid owned teacher role snapshot')
                sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES ('
                    + ','.join('CONVERT(0x' + value + ' USING utf8mb4)' for value in values) + ')')

        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a', 'student_b', 'admin'):
                api.login(actor)
            # Login may select the normal org_code. Bind the full account/table
            # baseline after login, before this probe changes authorization data.
            original_rows = snapshot()
            check('teacher fixture initially manages exact class A',
                  sql("SELECT depart_ids FROM sys_user WHERE id='fixture_teacher_a'") == 'fixture_class_a')
            check('teacher fixture initially has only the teacher role',
                  sql('SELECT r.role_code FROM sys_user_role ur JOIN sys_role r ON r.id=ur.role_id WHERE '
                      + teacher_where.replace('user_id', 'ur.user_id') + ' ORDER BY r.role_code') == 'teacher')
            check('probe task and course IDs are unused',
                  sql('SELECT COUNT(*) FROM teaching_additional_work WHERE id IN ('
                      + ','.join(literal(value) for value in task_ids) + ')') == '0'
                  and sql('SELECT COUNT(*) FROM teaching_course WHERE id=' + literal(prefix + '_course')) == '0')
            fixtures_owned = True
            for suffix, assigned, state in [('a', 'fixture_class_a', 1), ('b', 'fixture_class_b', 1),
                                            ('draft', 'fixture_class_a', 0), ('multi', 'fixture_class_a, fixture_class_b ', 1),
                                            ('prefix', 'fixture_class_a_extra', 1), ('case', 'FIXTURE_CLASS_A', 1),
                                            ('spaced', ' \tfixture_class_a\r\n , \tfixture_class_b \r\n', 1),
                                            ('interior', 'fixture_cl ass_a', 1),
                                            ('unicode_space', '\u00a0fixture_class_a\u00a0', 1),
                                            ('unicode_line', 'fixture_class_a\u2028', 1)]:
                insert('teaching_additional_work', id=prefix + '_' + suffix, work_name=prefix + '_' + suffix,
                       work_desc=sentinel, work_dept=assigned, status=state, create_by='fixture_teacher_a',
                       create_time='2026-10-11 00:00:00')
            insert('teaching_course', id=prefix + '_course', course_name=prefix + '_public', course_desc='public synthetic course',
                   show_home=1, is_shared=1, del_flag=0, create_by='fixture_admin', create_time='2026-10-11 00:00:00')
            seeded = snapshot()

            def allowed(name, endpoint, suffix, actor):
                status, result, _ = api.request('GET', BASE + endpoint + '?id=' + prefix + '_' + suffix, actor)
                check(name, status == 200 and result and result.get('success') is True
                      and result.get('result', {}).get('id') == prefix + '_' + suffix
                      and result['result'].get('workDesc') == sentinel)

            def denied(name, endpoint, suffix, actor):
                before = read_state()
                status, result, _ = api.request('GET', BASE + endpoint + '?id=' + prefix + '_' + suffix, actor)
                check(name, status == (200 if actor else 401) and result and result.get('success') is False
                      and result.get('code') == (510 if actor else 401) and not result.get('result')
                      and sentinel not in json.dumps(result))
                check(name + ' preserves business authorization rows cache and bytes', before == read_state())

            def retired(name, actor, path='teacherList', pagination=None):
                before = read_state()
                query = {'workName': '*' + prefix + '*', 'pageNo': 1, 'pageSize': 10,
                         'column': 'workName', 'order': 'asc', **(pagination or {})}
                status, body = raw_get(BASE + path + '?' + urlencode(query), actor)
                if expect_legacy_teacher_list and actor:
                    try:
                        result = json.loads(body)
                    except ValueError:
                        result = None
                    check(name + ' reproduces creator-only disclosure', status == 200 and isinstance(result, dict)
                          and result.get('success') is True and any(
                              row.get('id') == prefix + '_draft' and row.get('workDesc') == sentinel
                              for row in result.get('result', {}).get('records', [])))
                else:
                    check(name + ' has no entity response', status in ((400, 404) if actor else (400, 401, 404))
                          and sentinel not in body and all(value not in body for value in task_ids))
                after = read_state()
                if expect_legacy_teacher_list and actor:
                    # A successful old route may warm dictionary caches while
                    # serializing the leaked entity. Cache preservation is a
                    # required assertion for rejection on the fixed route.
                    check(name + ' preserves business authorization rows and bytes',
                          before[0] == after[0] and before[2] == after[2])
                else:
                    check(name + ' preserves business authorization rows cache and bytes', before == after)

            def current_list(name, actor, suffix):
                query = {'workName': prefix + '_' + suffix, 'pageNo': 1, 'pageSize': 1,
                         'column': 'id', 'order': 'asc'}
                status, result, _ = api.request('GET', BASE + 'list?' + urlencode(query), actor)
                check(name, status == 200 and result and result.get('success') is True
                      and result.get('result', {}).get('total') == 1
                      and [row.get('id') for row in result['result']['records']] == [prefix + '_' + suffix])
                status, result, _ = api.request('GET', BASE + 'list?' + urlencode(dict(query, pageNo=2)), actor)
                check(name + ' retains filtered pagination', status == 200 and result and result.get('success') is True
                      and result.get('result', {}).get('total') == 1 and result['result']['records'] == [])

            def excluded_from_list(name, actor, suffix):
                before = read_state()
                query = {'workName': prefix + '_' + suffix, 'pageNo': 1, 'pageSize': 1}
                status, result, _ = api.request('GET', BASE + 'list?' + urlencode(query), actor)
                check(name, status == 200 and result and result.get('success') is True
                      and result.get('result', {}).get('total') == 0 and result['result']['records'] == []
                      and sentinel not in json.dumps(result))
                check(name + ' preserves business authorization rows cache and bytes', before == read_state())

            def management_denied(name, actor, path='list', legacy_empty_scope=False):
                before = read_state()
                query = {'workName': prefix + '_draft', 'pageNo': 1, 'pageSize': 1}
                status, body = raw_get(BASE + path + '?' + urlencode(query), actor)
                try:
                    result = json.loads(body)
                except ValueError:
                    result = None
                expected_codes = (500, 510) if legacy_empty_scope and expect_legacy_management_list else (510,)
                check(name, ((status == 200 and result and result.get('success') is False
                              and result.get('code') in expected_codes and not result.get('result'))
                             or (status in (400, 404) and path != 'list')
                             or (not actor and status == 401))
                      and sentinel not in body and all(value not in body for value in task_ids))
                check(name + ' preserves business authorization rows cache and bytes', before == read_state())

            def scoped_pages(name, actor, suffixes):
                expected = [prefix + '_' + suffix for suffix in sorted(suffixes)]
                observed = []
                for page_no in range(1, len(expected) + 2):
                    query = {'workName': '*' + prefix + '*', 'pageNo': page_no, 'pageSize': 1,
                             'column': 'id', 'order': 'asc'}
                    status, result, _ = api.request('GET', BASE + 'list?' + urlencode(query), actor)
                    rows = result.get('result', {}) if result else {}
                    wanted = expected[page_no - 1:page_no]
                    ids = [row.get('id') for row in rows.get('records', [])]
                    check(name + ' page ' + str(page_no), status == 200 and result and result.get('success') is True
                          and rows.get('total') == len(expected) and ids == wanted)
                    observed.extend(ids)
                check(name + ' returns every permitted row exactly once', observed == expected)

            for endpoint in ('queryById', 'getWorkInfo'):
                if expect_legacy_details:
                    allowed(endpoint + ' baseline exposes foreign published assignment to student', endpoint, 'b', 'student_a')
                    allowed(endpoint + ' baseline exposes draft assignment to student', endpoint, 'draft', 'student_a')
                    allowed(endpoint + ' baseline exposes foreign task to teacher', endpoint, 'b', 'teacher_a')
                    continue
                for actor in ('student_a', 'teacher_a', 'admin'):
                    allowed(endpoint + ' permits assigned ' + actor, endpoint, 'a', actor)
                allowed(endpoint + ' permits teacher draft preview', endpoint, 'draft', 'teacher_a')
                allowed(endpoint + ' permits administrator foreign draft', endpoint, 'draft', 'admin')
                for actor in ('student_a', 'student_b', 'teacher_a', 'teacher_b'):
                    allowed(endpoint + ' permits assigned multi-class ' + actor, endpoint, 'multi', actor)
                    allowed(endpoint + ' trims CSV token edge whitespace for ' + actor, endpoint, 'spaced', actor)
                for actor in ('student_b', 'teacher_b'):
                    denied(endpoint + ' rejects cross-class ' + actor, endpoint, 'a', actor)
                denied(endpoint + ' rejects unpublished task for assigned student', endpoint, 'draft', 'student_a')
                denied(endpoint + ' does not use creator as class authorization', endpoint, 'b', 'teacher_a')
                denied(endpoint + ' requires exact class membership', endpoint, 'prefix', 'student_a')
                denied(endpoint + ' rejects class case alias', endpoint, 'case', 'teacher_a')
                denied(endpoint + ' preserves interior class whitespace', endpoint, 'interior', 'teacher_a')
                denied(endpoint + ' preserves Unicode token edge spaces', endpoint, 'unicode_space', 'teacher_a')
                denied(endpoint + ' preserves final Unicode line separator', endpoint, 'unicode_line', 'teacher_a')
                denied(endpoint + ' does not publish assignment anonymously', endpoint, 'a', None)
                denied(endpoint + ' rejects unknown ID', endpoint, 'missing', 'student_a')
                status, result, _ = api.request('GET', BASE + endpoint + '?id=' + (prefix + '_a').upper(), 'student_a')
                check(endpoint + ' rejects database collation ID alias', status == 200 and result and result.get('success') is False
                      and result.get('code') == 510 and not result.get('result'))

            current_list('current teacher list remains usable', 'teacher_a', 'a')
            current_list('current class B teacher list remains usable', 'teacher_b', 'b')
            current_list('current administrator list remains usable', 'admin', 'b')
            current_list('teacher keeps legitimate draft list', 'teacher_a', 'draft')
            current_list('teacher keeps whitespace-padded CSV assignment', 'teacher_a', 'spaced')
            for suffix in ('prefix', 'case', 'unicode_space', 'unicode_line'):
                if expect_legacy_management_list:
                    current_list('baseline list exposes class alias ' + suffix, 'teacher_a', suffix)
                else:
                    excluded_from_list('management list rejects class alias ' + suffix, 'teacher_a', suffix)
            excluded_from_list('management list preserves interior token whitespace', 'teacher_a', 'interior')
            teacher_a_scope = ('a', 'draft', 'multi', 'spaced') + (('prefix', 'case', 'unicode_space', 'unicode_line')
                                                                if expect_legacy_management_list else ())
            scoped_pages('teacher A exact authorized count and pagination', 'teacher_a', teacher_a_scope)
            scoped_pages('teacher B exact authorized count and pagination', 'teacher_b', ('b', 'multi', 'spaced'))
            scoped_pages('administrator retains all filtered records', 'admin', task_suffixes)
            management_denied('student cannot use management list', 'student_a', legacy_empty_scope=True)
            management_denied('anonymous cannot use management list', None)
            retired('current author cannot use retired teacher list', 'teacher_a')
            if not expect_legacy_teacher_list:
                for actor in ('student_a', 'admin', None):
                    retired('retired teacher list rejects ' + (actor or 'anonymous'), actor)
                for path in RETIRED_PATHS[1:]:
                    retired('retired teacher list rejects alias ' + path, 'teacher_a', path)
                retired('retired teacher list rejects a later bounded page', 'teacher_a', pagination={'pageNo': 2, 'pageSize': 100})

            original_token = api.tokens['teacher_a']
            for label, department in [('removed management class', ''), ('transferred management class', 'fixture_class_b')]:
                department_changed = True
                sql("UPDATE sys_user SET depart_ids=" + literal(department) + " WHERE id='fixture_teacher_a'")
                check(label + ' is tested with the original JWT', api.tokens['teacher_a'] == original_token)
                for path in (('teacherList',) if expect_legacy_teacher_list else RETIRED_PATHS):
                    retired(label + ' old author route ' + path, 'teacher_a', path)
                if not expect_legacy_details:
                    for endpoint in ('queryById', 'getWorkInfo'):
                        denied(label + ' cannot preview old class draft through ' + endpoint, endpoint, 'draft', 'teacher_a')
                if department:
                    excluded_from_list(label + ' cannot list old class draft', 'teacher_a', 'draft')
                    current_list(label + ' can list newly managed class', 'teacher_a', 'b')
                    scoped_pages(label + ' retains only new class count', 'teacher_a', ('b', 'multi', 'spaced'))
                else:
                    management_denied(label + ' rejects management list', 'teacher_a', legacy_empty_scope=True)
            restore_department()
            student_role = sql("SELECT id FROM sys_role WHERE role_code='student' ORDER BY id")
            check('one exact synthetic student role is available', bool(student_role) and '\n' not in student_role)
            roles_changed = True
            sql('DELETE FROM sys_user_role WHERE ' + teacher_where)
            insert('sys_user_role', id=prefix + '_role', user_id='fixture_teacher_a', role_id=student_role)
            check('old author now has only the student role',
                  sql('SELECT r.role_code FROM sys_user_role ur JOIN sys_role r ON r.id=ur.role_id WHERE '
                      + teacher_where.replace('user_id', 'ur.user_id') + ' ORDER BY r.role_code') == 'student')
            check('teacher role revocation uses the original JWT', api.tokens['teacher_a'] == original_token)
            for path in (('teacherList',) if expect_legacy_teacher_list else RETIRED_PATHS):
                retired('revoked teacher old author route ' + path, 'teacher_a', path)
            if not expect_legacy_details:
                for endpoint in ('queryById', 'getWorkInfo'):
                    denied('revoked teacher cannot preview old draft through ' + endpoint, endpoint, 'draft', 'teacher_a')
            if expect_legacy_management_list:
                current_list('baseline revoked teacher original JWT still exposes old draft', 'teacher_a', 'draft')
            else:
                for path in MANAGEMENT_PATHS:
                    management_denied('revoked teacher original JWT cannot use management route ' + path,
                                      'teacher_a', path)
            restore_roles()
            if not expect_legacy_details:
                for endpoint in ('queryById', 'getWorkInfo'):
                    allowed('restored teacher keeps legitimate draft detail ' + endpoint, endpoint, 'draft', 'teacher_a')
            current_list('restored teacher keeps legitimate list', 'teacher_a', 'a')

            status, result, _ = api.request('GET', '/teaching/teachingCourse/queryById?id=' + prefix + '_course', 'student_b')
            check('shared public course remains readable without class assignment', status == 200 and result
                  and result.get('success') is True and result.get('result', {}).get('id') == prefix + '_course')
            status, result, _ = api.request('GET', '/teaching/teachingCourse/getHomeCourse?courseName=' + prefix + '_public')
            check('anonymous public-course discovery remains available', status == 200 and result and result.get('success') is True
                  and any(row.get('id') == prefix + '_course' for row in result['result']['records']))
            check('allowed and rejected reads preserve all business rows', seeded == snapshot())
            check('allowed and rejected reads preserve all uploaded bytes', original_files == file_snapshot())
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            try:
                if department_changed:
                    restore_department()
                if roles_changed:
                    restore_roles()
                if fixtures_owned:
                    sql('DELETE FROM teaching_additional_work WHERE id IN (' + ','.join(literal(value) for value in task_ids) + ')')
                    sql('DELETE FROM teaching_course WHERE id=' + literal(prefix + '_course'))
            except Exception as failure:
                cleanup_error = 'Cleanup ' + type(failure).__name__ + ': ' + str(failure)
                error = (error + '; ' if error else '') + cleanup_error
        check('all original business rows restored', original_rows == snapshot(), fatal=False)
        check('all original upload bytes restored', original_files == file_snapshot(), fatal=False)
        result = {'cases': cases, 'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases),
                  'total': len(cases), 'jar_sha256': api.jar_sha256, 'expected_legacy': expect_legacy_details,
                  'expected_legacy_teacher_list': expect_legacy_teacher_list, 'exception': error, 'completed': error is None,
                  'expected_legacy_management_list': expect_legacy_management_list,
                  'production_connected': False,
                  'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'created_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Actual HTTP assignment details and management list exact CSV class scope, SQL pagination/count, retired creator-list aliases; same-token class/role revocation; owned synthetic fixture only.',
                  'database_baseline': 'Full business and authorization tables after synthetic login, before probe fixture changes; normal sys_log retained.',
                  'denial_cache_scope': 'Configured Redis DB 1 key membership and serialized values except userToken sessions and CAPTCHA keys; ticking TTLs excluded.',
                  'cache_transition': 'No explicit cache eviction between authorization changes and old-token requests; normal FixtureApi logout cleanup.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    parser.add_argument('--expect-legacy-teacher-list', action='store_true',
                        help='Reproduce the creator-only list on a pre-retirement JAR while keeping current detail authorization checks')
    parser.add_argument('--expect-legacy-management-list', action='store_true',
                        help='Reproduce management-list role revocation and prefix/case leakage on a pre-scope-fix JAR')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
